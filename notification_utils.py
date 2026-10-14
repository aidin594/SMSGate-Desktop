"""Detect *new* incoming SMS without false backfill or cross-SIM alerts.

No Qt, no networking, and no plaintext message content is persisted by this module.
"""
from __future__ import annotations

from core import normalized_sim, unique_key


class IncomingNotificationTracker:
    def __init__(self) -> None:
        self._ready = False
        self._known: set[tuple] = set()

    @property
    def ready(self) -> bool:
        return self._ready

    def ingest(self, inbox_items: list[dict], selected_sim: int,
               include_unknown_sim: bool = False) -> list[dict]:
        """Return unseen selected-SIM arrivals after initial successful inbox fetch.

        First successful fetch establishes the baseline and never alerts for
        historical messages, including after restarting the application.
        Newly fetched messages for the other SIM are tracked, but never alert.
        Failed fetches should never call this method (no baseline established).
        """
        fresh = []
        current = set()
        for item in inbox_items:
            if not isinstance(item,dict) or item.get('direction')!='incoming':
                continue
            key = unique_key(item)
            if key in current:
                continue
            current.add(key)
            if not self._ready or key in self._known:
                continue
            slot = normalized_sim(item.get('sim'))
            if slot == selected_sim or (slot is None and include_unknown_sim):
                fresh.append(item)
        self._known.update(current)
        if not self._ready:
            self._ready=True
            return []
        return sorted(fresh, key=lambda x: str(x.get('date','')))


def alert_content(items: list[dict], show_preview: bool) -> tuple[str,str]:
    """Text for a single OS notification, bounded and privacy-aware."""
    if not items:
        return '', ''
    if len(items)>1:
        return f'{len(items)} new messages', 'Open SMSGate Desk to read your new messages.'
    item=items[0]
    who=str(item.get('phone') or 'Unknown sender')[:90]
    body=' '.join(str(item.get('text') or '').split())
    return f'New SMS · {who}', (body[:180] + ('…' if len(body)>180 else '')) if (show_preview and body) else 'Open SMSGate Desk to read the message.'
