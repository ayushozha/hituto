from reboot.api import API, Field, Methods, Model, Reader, Transaction, Type, Workflow, Writer


class TutorSessionState(Model):
    question_text: str = Field(tag=1, default="")
    source_kind: str = Field(tag=2, default="")
    lesson_json: str = Field(tag=3, default="")
    status: str = Field(tag=4, default="")
    error_message: str = Field(tag=5, default="")
    revision: int = Field(tag=6, default=0)
    last_student_message: str = Field(tag=7, default="")
    generation: int = Field(tag=8, default=0)
    voice_generation: int = Field(tag=9, default=0)
    voice_status: str = Field(tag=10, default="")
    voice_error: str = Field(tag=11, default="")
    voice_token_ciphertext_id: str = Field(tag=12, default="")
    tts_model: str = Field(tag=13, default="")
    message_index_id: str = Field(tag=14, default="")
    chat_revision: int = Field(tag=15, default=0)
    message_count: int = Field(tag=16, default=0)
    # The authenticated account this session belongs to. Stamped by `ensure`
    # on first use; afterwards no other account may read or write the session.
    owner_id: str = Field(tag=17, default="")
    # Bumped by `forget`. Crypto-shredding is irreversible, so the scope it
    # destroys must never be reused — otherwise voice stays broken forever
    # after a student erases their data.
    crypto_epoch: int = Field(tag=18, default=0)


class TutorMessageState(Model):
    role: str = Field(tag=1, default="")
    text: str = Field(tag=2, default="")
    lesson_json: str = Field(tag=3, default="")
    source_kind: str = Field(tag=4, default="")
    generation: int = Field(tag=5, default=0)
    status: str = Field(tag=6, default="")


class SnapshotResponse(Model):
    question_text: str = Field(tag=1, default="")
    source_kind: str = Field(tag=2, default="")
    lesson_json: str = Field(tag=3, default="")
    status: str = Field(tag=4, default="")
    error_message: str = Field(tag=5, default="")
    revision: int = Field(tag=6, default=0)
    last_student_message: str = Field(tag=7, default="")
    generation: int = Field(tag=8, default=0)
    voice_generation: int = Field(tag=9, default=0)
    voice_status: str = Field(tag=10, default="")
    voice_error: str = Field(tag=11, default="")


class StartLessonRequest(Model):
    question_text: str = Field(tag=1, default="")
    source_kind: str = Field(tag=2, default="")
    source_media_type: str = Field(tag=3, default="")
    source_base64: str = Field(tag=4, default="")


class StartLessonResponse(Model):
    generation: int = Field(tag=1, default=0)


class PrepareLessonRequest(Model):
    question_text: str = Field(tag=1, default="")
    source_kind: str = Field(tag=2, default="")
    source_media_type: str = Field(tag=3, default="")
    source_base64: str = Field(tag=4, default="")
    generation: int = Field(tag=5, default=0)


class StartReplanRequest(Model):
    student_message: str = Field(tag=1, default="")
    completed_beat_index: int = Field(tag=2, default=0)
    source_media_type: str = Field(tag=3, default="")
    source_base64: str = Field(tag=4, default="")


class StartReplanResponse(Model):
    generation: int = Field(tag=1, default=0)


class ReplanLessonRequest(Model):
    student_message: str = Field(tag=1, default="")
    completed_beat_index: int = Field(tag=2, default=0)
    source_media_type: str = Field(tag=3, default="")
    source_base64: str = Field(tag=4, default="")
    generation: int = Field(tag=5, default=0)


class CheckWorkRequest(Model):
    student_work: str = Field(tag=1, default="")
    # The question this working belongs to. Empty means "the one this session
    # is already on".
    question_text: str = Field(tag=2, default="")


class CheckWorkResponse(Model):
    generation: int = Field(tag=1, default=0)


class ReviewWorkRequest(Model):
    student_work: str = Field(tag=1, default="")
    generation: int = Field(tag=2, default=0)
    question_text: str = Field(tag=3, default="")


class RequestVoiceTokenResponse(Model):
    generation: int = Field(tag=1, default=0)


class GrantVoiceTokenRequest(Model):
    generation: int = Field(tag=1, default=0)


class ConsumeVoiceTokenRequest(Model):
    generation: int = Field(tag=1, default=0)


class ConsumeVoiceTokenResponse(Model):
    ok: bool = Field(tag=1, default=False)
    access_token: str = Field(tag=2, default="")
    expires_in: int = Field(tag=3, default=0)
    tts_model: str = Field(tag=4, default="")
    message: str = Field(tag=5, default="")


class ChatMessage(Model):
    id: str = Field(tag=1, default="")
    role: str = Field(tag=2, default="")
    text: str = Field(tag=3, default="")
    lesson_json: str = Field(tag=4, default="")
    source_kind: str = Field(tag=5, default="")
    generation: int = Field(tag=6, default=0)
    status: str = Field(tag=7, default="")


class MessagesRequest(Model):
    cursor: str = Field(tag=1, default="")
    limit: int = Field(tag=2, default=0)


class MessagesResponse(Model):
    messages: list[ChatMessage] = Field(tag=1, default_factory=list)
    next_cursor: str = Field(tag=2, default="")


class SetTutorMessageRequest(Model):
    role: str = Field(tag=1, default="")
    text: str = Field(tag=2, default="")
    lesson_json: str = Field(tag=3, default="")
    source_kind: str = Field(tag=4, default="")
    generation: int = Field(tag=5, default=0)
    status: str = Field(tag=6, default="")


class TutorMessageSnapshotResponse(Model):
    id: str = Field(tag=1, default="")
    role: str = Field(tag=2, default="")
    text: str = Field(tag=3, default="")
    lesson_json: str = Field(tag=4, default="")
    source_kind: str = Field(tag=5, default="")
    generation: int = Field(tag=6, default=0)
    status: str = Field(tag=7, default="")


class UsageLedgerState(Model):
    """Per-account usage, so provider spend has a ceiling."""

    lessons_today: int = Field(tag=1, default=0)
    checks_today: int = Field(tag=2, default=0)
    recent_calls: int = Field(tag=3, default=0)
    day_reset_scheduled: bool = Field(tag=4, default=False)
    window_reset_scheduled: bool = Field(tag=5, default=False)


class ConsumeRequest(Model):
    # "check" for a work check; anything else counts as a lesson. Reboot only
    # allows a field's zero value as its default.
    kind: str = Field(tag=1, default="")


class ConsumeResponse(Model):
    allowed: bool = Field(tag=1, default=False)
    message: str = Field(tag=2, default="")


class UsageSnapshotResponse(Model):
    lessons_today: int = Field(tag=1, default=0)
    checks_today: int = Field(tag=2, default=0)
    recent_calls: int = Field(tag=3, default=0)


UsageLedgerMethods = Methods(
    consume=Writer(request=ConsumeRequest, response=ConsumeResponse, mcp=None),
    reset_day=Writer(request=None, response=None, mcp=None),
    reset_window=Writer(request=None, response=None, mcp=None),
    snapshot=Reader(request=None, response=UsageSnapshotResponse, mcp=None),
)


class ForgetResponse(Model):
    messages_erased: int = Field(tag=1, default=0)
    more_remaining: bool = Field(tag=2, default=False)


TutorSessionMethods = Methods(
    ensure=Writer(request=None, response=None, mcp=None),
    snapshot=Reader(request=None, response=SnapshotResponse, mcp=None),
    messages=Reader(
        request=MessagesRequest,
        response=MessagesResponse,
        mcp=None,
    ),
    start_lesson=Transaction(
        request=StartLessonRequest,
        response=StartLessonResponse,
        mcp=None,
    ),
    prepare_lesson=Workflow(
        request=PrepareLessonRequest,
        response=None,
        mcp=None,
    ),
    start_replan=Transaction(
        request=StartReplanRequest,
        response=StartReplanResponse,
        mcp=None,
    ),
    replan_lesson=Workflow(
        request=ReplanLessonRequest,
        response=None,
        mcp=None,
    ),
    check_work=Transaction(
        request=CheckWorkRequest,
        response=CheckWorkResponse,
        mcp=None,
    ),
    review_work=Workflow(
        request=ReviewWorkRequest,
        response=None,
        mcp=None,
    ),
    request_voice_token=Writer(
        request=None,
        response=RequestVoiceTokenResponse,
        mcp=None,
    ),
    grant_voice_token=Workflow(
        request=GrantVoiceTokenRequest,
        response=None,
        mcp=None,
    ),
    consume_voice_token=Writer(
        request=ConsumeVoiceTokenRequest,
        response=ConsumeVoiceTokenResponse,
        mcp=None,
    ),
    reset=Writer(request=None, response=None, mcp=None),
    forget=Transaction(request=None, response=ForgetResponse, mcp=None),
)


TutorMessageMethods = Methods(
    set=Writer(request=SetTutorMessageRequest, response=None, mcp=None),
    snapshot=Reader(request=None, response=TutorMessageSnapshotResponse, mcp=None),
)


api = API(
    TutorSession=Type(
        state=TutorSessionState,
        methods=TutorSessionMethods,
    ),
    TutorMessage=Type(
        state=TutorMessageState,
        methods=TutorMessageMethods,
    ),
    UsageLedger=Type(
        state=UsageLedgerState,
        methods=UsageLedgerMethods,
    ),
)
