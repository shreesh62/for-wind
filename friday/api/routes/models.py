"""Model router info routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from friday.api.schemas.models import ModelInfoSchema, ModelsResponse


def build_router(ctx, auth) -> APIRouter:
    """Build the models router."""
    router = APIRouter(prefix="/api", tags=["models"])

    @router.get("/models", response_model=ModelsResponse, dependencies=[Depends(auth)])
    async def get_models() -> ModelsResponse:
        """List available models, providers, and usage stats."""
        if not ctx.model_router:
            return ModelsResponse()

        providers = ctx.model_router.get_available_providers()
        models = []
        for provider_name in providers:
            p = ctx.model_router._providers.get(provider_name)
            if p:
                for m in p.models:
                    models.append(ModelInfoSchema(
                        provider=m.provider,
                        model_id=m.model_id,
                        capabilities=[c.value for c in m.capabilities],
                        priority=m.priority,
                    ))

        return ModelsResponse(
            providers=providers,
            models=models,
            usage=ctx.model_router.get_usage_stats(),
        )

    return router
