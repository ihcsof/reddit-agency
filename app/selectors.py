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

COMMENT_TRIGGER = (
    'button:has-text("Join the conversation"), '
    '[role="button"]:has-text("Join the conversation"), '
    'button:has-text("Add a comment"), '
    '[role="button"]:has-text("Add a comment"), '
    'button:has-text("Comment"), '
    '[role="button"]:has-text("Comment")'
)

COMMENT_TEXTBOX = (
    'shreddit-composer div[contenteditable="true"][role="textbox"]:visible, '
    'shreddit-composer div[contenteditable="true"][data-lexical-editor="true"]:visible, '
    'div[contenteditable="true"][role="textbox"][aria-placeholder="Join the conversation"]:visible, '
    'div[contenteditable="true"][data-lexical-editor="true"][aria-placeholder="Join the conversation"]:visible'
)

COMMENT_SUBMIT = 'shreddit-composer button[slot="submit-button"][type="submit"]:visible'

__all__ = [
    "COMMENT_TRIGGER",
    "COMMENT_SUBMIT",
    "COMMENT_TEXTBOX",
    "COPY_LINK_OPTION",
    "SHARE_BUTTON",
    "VOTE_BUTTON",
]
