import asyncio

from viam.module.module import Module

from .driver import PlaygroundDriver  # noqa: F401  (registers the model)
from .service import SceneSprites  # noqa: F401  (registers the model)
from .simple_scene_example import SimpleSceneExample  # noqa: F401  (registers the model)
from .visualizer import PlaygroundVisualizer  # noqa: F401  (registers the model)


if __name__ == "__main__":
    asyncio.run(Module.run_from_registry())
