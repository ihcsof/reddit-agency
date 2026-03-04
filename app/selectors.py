from __future__ import annotations

VOTE_BUTTON = (
    'button[upvote], '
    'button:has(svg[icon-name="upvote"]), '
    '[role="button"]:has(svg[icon-name="upvote"])'
)

SHARE_BUTTON = (
    'button:has(svg[icon-name="share"]), '
    'button:has(.icon-share), '
    '[role="button"]:has(svg[icon-name="share"]), '
    '[role="button"]:has(.icon-share)'
)

COPY_LINK_OPTION = ".share-menu-copy-link-option"

COMMENT_TEXTBOX = 'shreddit-composer div[contenteditable="true"][role="textbox"]:visible'

COMMENT_SUBMIT = 'shreddit-composer button[slot="submit-button"][type="submit"]:visible'

__all__ = [
    "COMMENT_SUBMIT",
    "COMMENT_TEXTBOX",
    "COPY_LINK_OPTION",
    "SHARE_BUTTON",
    "VOTE_BUTTON",
]
