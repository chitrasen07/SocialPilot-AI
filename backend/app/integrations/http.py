import httpx


def create_http_client() -> httpx.AsyncClient:
    """Shared, pooled client for outbound platform APIs."""
    return httpx.AsyncClient(timeout=httpx.Timeout(10.0, connect=5.0))
