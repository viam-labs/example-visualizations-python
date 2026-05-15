"""Private implementation details. Not part of the public API.

Future steps will move asset loaders (STL→PLY, PCD writer, PLY
vertex-color extractor) and the metadata struct builder here, so the
public ``viam_visuals`` surface stays small and focused.

Nothing in this subpackage should be imported by external callers —
the surface is implementation-only and may change between releases.
"""
