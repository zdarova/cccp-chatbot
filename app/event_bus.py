"""Reactive Event Bus over Azure Event Hubs.

Implements event-driven patterns for streaming call processing:
- Event Sourcing: every event published to Event Hubs (immutable log)
- CQRS: write to Event Hubs, read from consumer groups
- Reactive Agents: subscribe to event types, react autonomously
- Fan-out: one event triggers multiple agents via consumer groups

Event Hubs topic: call-transcripts (already deployed)
"""

import os
import json
import time
import asyncio
import logging
from dataclasses import dataclass, field
from typing import Callable
from collections import defaultdict

logger = logging.getLogger(__name__)


@dataclass
class CallEvent:
    """Immutable event in the call processing stream."""
    event_type: str          # utterance.customer, sentiment.negative, action.suggestion
    call_id: str
    timestamp: float = field(default_factory=time.time)
    data: dict = field(default_factory=dict)
    source_agent: str = ""

    def to_json(self) -> str:
        return json.dumps({
            "event_type": self.event_type,
            "call_id": self.call_id,
            "timestamp": self.timestamp,
            "data": self.data,
            "source_agent": self.source_agent,
        })

    @classmethod
    def from_json(cls, raw: str) -> "CallEvent":
        d = json.loads(raw)
        return cls(**d)


class EventHubBus:
    """Event bus backed by Azure Event Hubs.

    Write path: publish events to Event Hub (event sourcing)
    Read path: consume events and dispatch to reactive agents
    """

    def __init__(self):
        self._subscribers: dict[str, list[Callable]] = defaultdict(list)
        self._local_log: list[CallEvent] = []
        self._producer = None
        self._consumer = None

    def _get_producer(self):
        if self._producer is None:
            try:
                from azure.eventhub import EventHubProducerClient
                conn = os.environ.get("EVENT_HUB_CONNECTION", "")
                if conn:
                    self._producer = EventHubProducerClient.from_connection_string(
                        conn, eventhub_name="call-transcripts"
                    )
            except Exception as e:
                logger.warning(f"Event Hub producer init failed: {e}")
        return self._producer

    def subscribe(self, event_type: str, handler: Callable):
        """Subscribe a reactive agent to an event type pattern."""
        self._subscribers[event_type].append(handler)

    async def publish(self, event: CallEvent):
        """Publish event to Event Hub + dispatch to local subscribers."""
        # Store locally (for in-process reactive agents)
        self._local_log.append(event)

        # Publish to Event Hub (event sourcing - durable log)
        producer = self._get_producer()
        if producer:
            try:
                from azure.eventhub import EventData
                batch = await asyncio.to_thread(producer.create_batch)
                batch.add(EventData(event.to_json()))
                await asyncio.to_thread(producer.send_batch, batch)
            except Exception as e:
                logger.warning(f"Event Hub publish failed: {e}")

        # Fan-out to local reactive agents
        tasks = []
        for pattern, handlers in self._subscribers.items():
            if self._matches(event.event_type, pattern):
                for handler in handlers:
                    tasks.append(self._safe_dispatch(handler, event))
        if tasks:
            await asyncio.gather(*tasks)

    async def _safe_dispatch(self, handler: Callable, event: CallEvent):
        try:
            result = handler(event)
            if asyncio.iscoroutine(result):
                await result
        except Exception as e:
            logger.warning(f"Handler failed for {event.event_type}: {e}")

    def _matches(self, event_type: str, pattern: str) -> bool:
        if pattern == "*":
            return True
        if pattern.endswith(".*"):
            return event_type.startswith(pattern[:-2])
        return event_type == pattern

    def get_call_events(self, call_id: str, limit: int = 50) -> list[dict]:
        """Query local event log for a call (CQRS read side)."""
        events = [e for e in self._local_log if e.call_id == call_id]
        return [{"type": e.event_type, "time": e.timestamp, "source": e.source_agent, "data": e.data}
                for e in events[-limit:]]

    def get_metrics(self) -> dict:
        """Aggregate metrics from event log."""
        counts = defaultdict(int)
        for e in self._local_log:
            counts[e.event_type] += 1
        return dict(counts)


# --- Reactive Agents ---

class ReactiveAgent:
    """Base class for event-driven reactive agents."""

    def __init__(self, name: str, bus: EventHubBus):
        self.name = name
        self.bus = bus

    def subscribe(self, event_type: str):
        self.bus.subscribe(event_type, self.handle)

    async def handle(self, event: CallEvent):
        raise NotImplementedError

    async def emit(self, event_type: str, call_id: str, data: dict):
        await self.bus.publish(CallEvent(
            event_type=event_type, call_id=call_id,
            data=data, source_agent=self.name,
        ))


class SentimentReactiveAgent(ReactiveAgent):
    """Reacts to customer utterances → emits sentiment events."""

    def __init__(self, bus: EventHubBus):
        super().__init__("sentiment_reactor", bus)
        self.subscribe("utterance.customer")

    async def handle(self, event: CallEvent):
        text = event.data.get("text", "")
        negative_words = ["problema", "reclamo", "inaccettabile", "disdetta", "vergogna", "ridicolo"]
        positive_words = ["grazie", "perfetto", "ottimo", "soddisfatto", "eccellente"]

        neg = sum(1 for w in negative_words if w in text.lower())
        pos = sum(1 for w in positive_words if w in text.lower())
        score = (pos - neg) / max(pos + neg, 1)
        sentiment = "negative" if score < -0.2 else "positive" if score > 0.2 else "neutral"

        await self.emit(f"sentiment.{sentiment}", event.call_id, {
            "score": round(score, 2), "sentiment": sentiment, "text_snippet": text[:80],
        })

        if score < -0.6:
            await self.emit("alert.escalation", event.call_id, {
                "reason": "Critical negative sentiment", "score": score,
            })


class SuggestionReactiveAgent(ReactiveAgent):
    """Reacts to negative sentiment → emits response suggestions."""

    def __init__(self, bus: EventHubBus):
        super().__init__("suggestion_reactor", bus)
        self.subscribe("sentiment.negative")

    async def handle(self, event: CallEvent):
        await self.emit("action.suggestion", event.call_id, {
            "suggestion": "Acknowledge frustration, offer concrete solution within 60s",
            "priority": "high",
            "trigger_score": event.data.get("score", 0),
        })


class CommercialReactiveAgent(ReactiveAgent):
    """Reacts to positive sentiment → flags upsell opportunity."""

    def __init__(self, bus: EventHubBus):
        super().__init__("commercial_reactor", bus)
        self.subscribe("sentiment.positive")

    async def handle(self, event: CallEvent):
        await self.emit("action.commercial", event.call_id, {
            "opportunity": "cross_sell",
            "message": "Customer positive - consider product suggestion after resolution",
        })


class AlertReactiveAgent(ReactiveAgent):
    """Reacts to escalation alerts → notifies supervisor."""

    def __init__(self, bus: EventHubBus):
        super().__init__("alert_reactor", bus)
        self.subscribe("alert.*")

    async def handle(self, event: CallEvent):
        logger.warning(f"[ALERT] Call {event.call_id}: {event.data.get('reason')}")
        await self.emit("notification.supervisor", event.call_id, {
            "priority": "HIGH",
            "action_required": True,
            "reason": event.data.get("reason", ""),
        })


# --- Factory ---

_bus_instance = None


def get_event_bus() -> EventHubBus:
    """Get or create the singleton event bus with all reactive agents wired."""
    global _bus_instance
    if _bus_instance is None:
        _bus_instance = EventHubBus()
        SentimentReactiveAgent(_bus_instance)
        SuggestionReactiveAgent(_bus_instance)
        CommercialReactiveAgent(_bus_instance)
        AlertReactiveAgent(_bus_instance)
    return _bus_instance
