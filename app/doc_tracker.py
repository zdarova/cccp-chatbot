"""Document tracker - persists file status in Cosmos DB.

Tracks: filename, type (pdf/audio), status (uploaded/indexing/indexed/error), timestamps.
"""

import os
import logging
from datetime import datetime, timezone

_container = None


def _get_container():
    global _container
    if _container is None:
        try:
            from azure.cosmos import CosmosClient
            endpoint = os.environ.get("COSMOS_ENDPOINT", "")
            key = os.environ.get("COSMOS_KEY", "")
            if not endpoint or not key:
                return None
            client = CosmosClient(endpoint, key)
            db = client.get_database_client("cccp")
            _container = db.get_container_client("documents")
        except Exception as e:
            logging.warning(f"Cosmos DB documents container not available: {e}")
            return None
    return _container


def track_document(filename: str, file_type: str = "pdf", status: str = "uploaded", size: int = 0, metadata: dict = None):
    """Create or update document status in Cosmos DB."""
    container = _get_container()
    if container is None:
        return
    try:
        doc = {
            "id": filename.replace("/", "-").replace(" ", "-"),
            "filename": filename,
            "type": file_type,
            "status": status,
            "size": size,
            "metadata": metadata or {},
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        if status == "uploaded":
            doc["uploaded_at"] = datetime.now(timezone.utc).isoformat()
        container.upsert_item(doc)
    except Exception as e:
        logging.warning(f"Failed to track document {filename}: {e}")


def update_status(filename: str, status: str, metadata: dict = None):
    """Update document status."""
    container = _get_container()
    if container is None:
        return
    try:
        doc_id = filename.replace("/", "-").replace(" ", "-")
        doc = container.read_item(doc_id, partition_key=filename)
        doc["status"] = status
        doc["updated_at"] = datetime.now(timezone.utc).isoformat()
        if metadata:
            doc["metadata"].update(metadata)
        container.upsert_item(doc)
    except Exception as e:
        logging.warning(f"Failed to update status for {filename}: {e}")


def list_tracked_documents(file_type: str = None) -> list[dict]:
    """List all tracked documents from Cosmos DB."""
    container = _get_container()
    if container is None:
        return []
    try:
        query = "SELECT * FROM c"
        params = []
        if file_type:
            query += " WHERE c.type = @type"
            params.append({"name": "@type", "value": file_type})

        items = list(container.query_items(
            query=query,
            parameters=params,
            enable_cross_partition_query=True,
        ))
        return [{
            "filename": i["filename"],
            "type": i["type"],
            "status": i["status"],
            "size": i.get("size", 0),
            "updated_at": i.get("updated_at", ""),
            "metadata": i.get("metadata", {}),
        } for i in items]
    except Exception as e:
        logging.warning(f"Failed to list documents: {e}")
        return []
