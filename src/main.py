import asyncio

from viam.module.module import Module

from .service import SceneSprites  # noqa: F401  (registers the model)


if __name__ == "__main__":
    asyncio.run(Module.run_from_registry())
