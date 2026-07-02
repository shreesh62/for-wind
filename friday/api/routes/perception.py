"""Perception / WorldState routes.

Exposes live perception so frontends and debuggers can see what FRIDAY
perceives. The planner reasons on WorldState, never raw pixels (ADR-014).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from friday.api.schemas.worldstate import WorldStateSchema


def build_router(ctx, auth) -> APIRouter:
    """Build the perception router."""
    router = APIRouter(prefix="/api", tags=["perception"])

    @router.get("/worldstate", response_model=WorldStateSchema, dependencies=[Depends(auth)])
    async def get_worldstate() -> WorldStateSchema:
        """Get a fresh WorldState snapshot — the current perception of the machine.

        Aggregates all perception sources (process/UIA/browser/screen/OCR).
        `semantic_coverage` indicates how much is semantic (DOM/UIA) vs visual.
        """
        if not ctx.bridge or not getattr(ctx.bridge, "engine", None):
            raise HTTPException(status_code=503, detail="Perception engine not available")

        try:
            snapshot = ctx.bridge.engine.perceive_as_dict()
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Perception failed: {exc}")

        return WorldStateSchema(
            timestamp=snapshot.get("timestamp", 0.0),
            window=snapshot.get("window"),
            app=snapshot.get("app"),
            cursor=list(snapshot.get("cursor", [0, 0])),
            focused=snapshot.get("focused"),
            ui_elements=snapshot.get("ui_elements", 0),
            ocr_regions=snapshot.get("ocr_regions", 0),
            browser_url=snapshot.get("browser_url"),
            browser_title=snapshot.get("browser_title"),
            browser_elements=snapshot.get("browser_elements", 0),
            derived=snapshot.get("derived", {}),
            state_hash=snapshot.get("state_hash", ""),
            sources=snapshot.get("sources", []),
            semantic_coverage=snapshot.get("semantic_coverage", 0.0),
        )

    return router
