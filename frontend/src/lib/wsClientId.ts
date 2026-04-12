// Stable per-page-load client ID shared between the WebSocket connection
// and the orchestrator chat POST so the backend can route stream tokens
// to the correct WS connection via manager.send_to(client_id, ...).
export const wsClientId = crypto.randomUUID()
