import os
from typing import Union

class Dir:

    @staticmethod
    def create_dir(paths: str, create: bool = True) -> str:
        try: 
            if create: os.makedirs(paths)
        except Exception as err: ...
        finally: return paths
        ...

    @staticmethod
    def basedir(path: str) -> str:
        return os.path.dirname(path)
        ...
        
    @staticmethod
    def extension(paths: Union[str, list]) -> list:
        if isinstance(paths, str):
            paths = [paths]

        seen = set()
        result = []
        for path in paths:
            ext = os.path.splitext(path)[1]
            if ext not in seen:
                seen.add(ext)
                result.append(ext)
        return result
