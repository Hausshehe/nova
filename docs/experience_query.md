# Nova Experience Query Layer

`trading_research/experience_query.py` is a read-only facade over Nova's research memory.

## Purpose

It lets future research components ask memory questions without directly mutating SQLite or gaining execution authority.

Supported questions include:

- what evidence exists for this frozen hypothesis;
- which dispositions were recorded;
- what evidence existed by a historical decision time;
- what a specific experiment recorded, including costs and segment decisions.

## Temporal rule

`available_history()` uses the experiment creation/observation timestamp and excludes any record observed after the requested decision time. This preserves the rule that later evidence cannot influence an earlier decision.

## Safety boundary

The query layer is read-only. It does not:

- run experiments;
- modify research memory;
- change research gates;
- promote strategies;
- authorize MT5 execution.

The returned knowledge class is descriptive. `PROMISING` historical research is not treated as `PROMOTED` strategy authority.
