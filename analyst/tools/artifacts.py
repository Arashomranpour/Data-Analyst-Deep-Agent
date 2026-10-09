import threading
from dataclasses import dataclass

import pandas as pd
from plotly.graph_objects import Figure


@dataclass
class QueryRecord:
    id: str
    title: str
    sql: str
    frame: pd.DataFrame


@dataclass
class ChartRecord:
    id: str
    title: str
    query_id: str
    figure: Figure


class Artifacts:
    """Everything the agent produced besides text: query results and charts.
    Written from agent worker threads, read by the Streamlit UI."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._queries: dict[str, QueryRecord] = {}
        self._charts: list[ChartRecord] = []

    def add_query(self, title: str, sql: str, frame: pd.DataFrame) -> str:
        with self._lock:
            qid = f"q{len(self._queries) + 1}"
            self._queries[qid] = QueryRecord(qid, title or qid, sql, frame)
            return qid

    def get_query(self, qid: str) -> QueryRecord | None:
        with self._lock:
            return self._queries.get(qid)

    def queries(self) -> list[QueryRecord]:
        with self._lock:
            return list(self._queries.values())

    def add_chart(self, title: str, query_id: str, figure: Figure) -> str:
        with self._lock:
            cid = f"c{len(self._charts) + 1}"
            self._charts.append(ChartRecord(cid, title, query_id, figure))
            return cid

    def charts(self) -> list[ChartRecord]:
        with self._lock:
            return list(self._charts)

    def clear(self) -> None:
        with self._lock:
            self._queries.clear()
            self._charts.clear()
