import json
from dataclasses import dataclass, asdict

@dataclass
class Metrics:
    node_count:int
    path_count:int
    width:int
    height:int
    notes:str = ""

    def to_json(self)->str:
        return json.dumps(asdict(self))
