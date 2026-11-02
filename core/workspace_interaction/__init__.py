"""SANTRA Unified Interaction Layer.
Exposes:
- WorkspaceManager: Folder resolution, safe creation, safe renaming, recent tracking.
- ApplicationManager: Executable discovery, process detection, window activation.
- BrowserInteractionManager: Chrome navigation, ChatGPT discovery, pinned chat routing, auth checks.
- ApplicationInteractionManager: Control inspection, safe clipboard text insertion, focus checks.
- DraftManager: Cryptographic draft binding, state machine, approval gates.
"""

from core.workspace_interaction.workspace_manager import (
    WorkspaceManager,
    workspace_manager,
)
from core.workspace_interaction.application_manager import (
    ApplicationManager,
    application_manager,
)
from core.workspace_interaction.browser_interaction_manager import (
    BrowserInteractionManager,
    browser_interaction_manager,
)
from core.workspace_interaction.application_interaction_manager import (
    ApplicationInteractionManager,
    application_interaction_manager,
)
from core.workspace_interaction.draft_manager import (
    DraftManager,
    DraftState,
    InteractionDraft,
    draft_manager,
)
from core.workspace_interaction.interaction_models import (
    ChatGPTConversationIdentity,
    WorkspaceIdentity,
    SubmissionVerificationStatus
)

__all__ = [
    "WorkspaceManager",
    "workspace_manager",
    "ApplicationManager",
    "application_manager",
    "BrowserInteractionManager",
    "browser_interaction_manager",
    "ApplicationInteractionManager",
    "application_interaction_manager",
    "DraftManager",
    "DraftState",
    "InteractionDraft",
    "draft_manager",
    "ChatGPTConversationIdentity",
    "WorkspaceIdentity",
    "SubmissionVerificationStatus"
]

