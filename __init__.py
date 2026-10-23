"""ComfyUI custom-node entry point."""

if __package__:
    from .apixly_media import NODE_CLASS_MAPPINGS, NODE_DISPLAY_NAME_MAPPINGS
else:
    from apixly_media import NODE_CLASS_MAPPINGS, NODE_DISPLAY_NAME_MAPPINGS

WEB_DIRECTORY = "./web"

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY"]
