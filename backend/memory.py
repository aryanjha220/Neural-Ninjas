from typing import Dict, List, Any

class SessionMemory:
    def __init__(self):
        self._sessions: Dict[str, List[Dict[str, Any]]] = {}

    def get_history(self, session_id: str, limit: int = 6) -> List[Dict[str, Any]]:
        return self._sessions.get(session_id, [])[-limit:]

    def add_turn(self, session_id: str, role: str, content: str, metadata: Dict[str, Any] = None) -> None:
        if session_id not in self._sessions:
            self._sessions[session_id] = []
        self._sessions[session_id].append({
            "role": role,
            "content": content,
            "metadata": metadata or {},
        })

session_memory = SessionMemory()