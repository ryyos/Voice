from __future__ import annotations

from typing import Any, List, Union

try:
    import jmespath as _jmespath
    _HAS_JMESPATH = True
except ImportError:
    _HAS_JMESPATH = False

from shared.utils.logger import log


class Search:
    """
    Utility class for searching nested dict/list structures.

    Search.deep(data, *path)          — stack-based deep traversal with
                                        multi-source and fallback-path support.
    Search.jpath(expression, data)    — JMESPath expression search.
    """

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _is_empty(value: Any) -> bool:
        if value is None:
            return True
        if isinstance(value, (list, dict, set, tuple)) and len(value) == 0:
            return True
        if isinstance(value, str) and value.strip() == "":
            return True
        return False

    # ------------------------------------------------------------------
    # Deep search
    # ------------------------------------------------------------------

    @staticmethod
    def deep(
        data: Any,
        *path: Union[str, List],
        return_first: bool = True,
        default: Any = None,
        debug: bool = False,
    ) -> Union[Any, List[Any], None]:
        """
        Deep search utility for nested dict/list structures.

        Supports three calling modes:

        1) Single source + single path
           Search.deep(data, "a", "b", "c")

        2) Single source + multi-path fallback
           Search.deep(data, ["uri"], ["browser_native_hd_url", "target", "url"])

        3) Multi-source + multi-path fallback
           Search.deep(
               [media_obj, "__typename"],
               [raw_data, "story", "url"],
           )

        Behavior:
        - Traverses nested dicts and lists iteratively (stack-based, no recursion).
        - Skips empty results (None, empty list, empty dict, empty string).
        - Stops early when return_first=True.
        - Returns default if no valid match found.
        - Debug logs only shown when debug=True.
        """
        if path and all(isinstance(p, list) for p in path):
            # Multi-source mode: each element is [source, *path]
            if all(len(p) >= 2 and isinstance(p[0], (dict, list)) for p in path):
                if debug:
                    log.debug(f"[deep] multi-source mode | sources={len(path)}")

                for idx, query in enumerate(path):
                    source, *single_path = query
                    if debug:
                        log.debug(f"[deep] source {idx + 1} | path={' -> '.join(single_path)}")

                    result = Search.deep(
                        source, *single_path,
                        return_first=return_first, default=None, debug=debug,
                    )
                    if result is not None:
                        return result

                return default

            # Fallback mode: each element is an alternative path for the same source
            else:
                if debug:
                    log.debug(f"[deep] fallback mode | paths={len(path)}")

                for idx, single_path in enumerate(path):
                    if debug:
                        log.debug(f"[deep] fallback {idx + 1} | path={' -> '.join(single_path)}")

                    result = Search.deep(
                        data, *single_path,
                        return_first=return_first, default=None, debug=debug,
                    )
                    if result is not None:
                        return result

                return default

        if not path:
            return default

        if debug:
            log.debug(f"[deep] start | path={' -> '.join(str(p) for p in path)}")

        results: list = []
        stack = [(data, 0)]
        visited = 0
        found = 0

        while stack:
            current, idx = stack.pop()
            visited += 1

            if isinstance(current, dict):
                key = path[idx]
                is_condition = isinstance(key, str) and key.startswith("!")
                condition_key = key[1:] if is_condition else None

                if not is_condition and key in current:
                    next_node = current[key]

                    if idx == len(path) - 1:
                        if is_condition:
                            if condition_key in current:
                                if debug:
                                    log.debug(f"[deep] condition '!{condition_key}' satisfied")
                                if not Search._is_empty(current):
                                    if return_first:
                                        return current
                                    results.append(current)
                            else:
                                if debug:
                                    log.warning(f"[deep] condition '!{condition_key}' failed")
                            continue

                        if not Search._is_empty(next_node):
                            found += 1
                            if debug:
                                log.success(f"[deep] match | type={type(next_node).__name__}")
                            if return_first:
                                if debug:
                                    log.debug(f"[deep] returning first | visited={visited}")
                                return next_node
                            results.append(next_node)
                        else:
                            if debug:
                                log.warning("[deep] empty match skipped")
                    else:
                        stack.append((next_node, idx + 1))

                for v in current.values():
                    if isinstance(v, (dict, list)):
                        stack.append((v, idx))

            elif isinstance(current, list):
                for item in current:
                    if isinstance(item, (dict, list)):
                        stack.append((item, idx))

        if debug:
            log.debug(f"[deep] done | visited={visited} | matches={found}")

        return default if return_first else (results or default)

    # ------------------------------------------------------------------
    # JMESPath search
    # ------------------------------------------------------------------

    @staticmethod
    def jpath(
        expression: str,
        data: Any,
        default: Any = None,
    ) -> Any:
        """
        Search using a JMESPath expression.

        Examples:
            Search.jpath("hits.results[*].id", data)
            Search.jpath("paging.next", data, default=0)

        Requires: pip install jmespath
        """
        if not _HAS_JMESPATH:
            raise ImportError("jmespath not installed — pip install jmespath")

        result = _jmespath.search(expression, data)
        return result if result is not None else default
