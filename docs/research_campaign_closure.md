# Current EURUSD research campaign closure

The current EURUSD daily campaign is closed after five frozen hypothesis families.

Dataset SHA-256:

`e4c70add8d77bcf5aa97ea9eeaa08d0fc8cc91679e6fd6a85ee3ad4a913b7f9e`

The planner must return `CAMPAIGN_CLOSED` when five frozen families are already recorded for this evidence source. A restart requires a materially new evidence source or a materially new market question.

This guard exists to prevent Nova from turning the completed campaign into an endless strategy-generation loop.
