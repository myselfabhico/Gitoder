"""Homepage: wordmark, greeting, the 2x2 SignatureCard grid, footer."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from .. import icons
from .. import theme as T
from ..widgets import (
    AvatarLabel,
    PaperSurface,
    SignatureCard,
    body_font,
    display_font,
    micro_font,
    stagger_entrance,
)

CARDS = [
    ("create", "Create Repo",
     "Start a brand-new repository and push your project to GitHub in a few clicks.",
     T.SURFACE),
    ("delete", "Delete Repo",
     "Pick any repository and remove it instantly, with no re-verification maze.",
     T.SURFACE_2),
    ("update", "Update Repo",
     "Swap an existing repo's files for your latest project folder.",
     T.HINT),
    ("download", "Download Repo",
     "Paste a repository link and get it as a ready-to-use .zip.",
     T.LINE),
]
CARD_POSITIONS = {(0, 0), (0, 1), (1, 0), (1, 1)}


class HomeScreen(PaperSurface):
    def __init__(self, ctx) -> None:
        super().__init__()
        self.ctx = ctx

        root = QVBoxLayout(self)
        root.setContentsMargins(64, 40, 64, 28)
        root.setSpacing(8)

        top = QHBoxLayout()
        self.avatar = AvatarLabel(34)
        top.addWidget(self.avatar)
        self.greet = QLabel("")
        self.greet.setFont(body_font(16, QFont.Medium))
        self.greet.setStyleSheet(f"color: {T.INK};")
        top.addSpacing(4)
        top.addWidget(self.greet)
        top.addStretch(1)
        root.addLayout(top)

        self.wordmark = QLabel("Gitoder")
        self.wordmark.setFont(display_font(84))
        self.wordmark.setStyleSheet(f"color: {T.INK};")
        root.addWidget(self.wordmark)

        self.tagline = QLabel("Git, minus the headaches.")
        self.tagline.setFont(body_font(18))
        self.tagline.setStyleSheet(f"color: {T.INK};")
        root.addWidget(self.tagline)

        root.addSpacing(12)

        grid_holder = QWidget()
        grid = QGridLayout(grid_holder)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(28)
        grid.setVerticalSpacing(24)
        for idx, (icon_name, heading, desc, surface) in enumerate(CARDS):
            card = SignatureCard(heading, desc, icon_name, surface=surface)
            card.clicked.connect(lambda _c=False, i=idx: self.ctx.go(i))
            row, col = divmod(idx, 2)
            grid.addWidget(card, row, col)
        self.grid = grid
        root.addWidget(grid_holder, 1)

        footer = QHBoxLayout()
        ver = QLabel("Gitoder v1.0")
        ver.setFont(micro_font())
        ver.setStyleSheet(f"color: {T.INK};")
        footer.addWidget(ver)
        footer.addStretch(1)
        token_link = QLabel('<a href="https://github.com/settings/tokens" '
                            'style="color:#AB7044">How do I get a token?</a>')
        token_link.setFont(micro_font())
        token_link.setOpenExternalLinks(True)
        footer.addWidget(token_link)
        root.addLayout(footer)

        stagger_entrance([self.wordmark, self.tagline, grid_holder])

    def refresh_user(self) -> None:
        user = self.ctx.user or {}
        self.greet.setText(f"Hey {user.get('name') or user.get('login', 'there')} — "
                           f"@{user.get('login', 'you')} ")
        self.avatar.set_initial(user.get("name") or user.get("login", "G"))
        av = user.get("avatar_url")
        if av:
            self.ctx.fetch_avatar(av, self.avatar.set_image_bytes)
