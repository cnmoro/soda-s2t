from google.protobuf.internal import containers as _containers
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class ExtendedSodaConfigMsg(_message.Message):
    __slots__ = ("channel_count", "sample_rate", "max_buffer_bytes", "simulate_realtime_testonly", "config_file_location", "api_key", "language_pack_directory", "recognition_mode", "reset_on_final_result", "include_timing_metrics", "enable_lang_id", "enable_formatting", "enable_speaker_change_detection", "include_logging", "multilang_config", "mask_offensive_words", "speaker_diarization_mode", "max_speaker_count", "recognition_context")
    class RecognitionMode(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
        __slots__ = ()
        UNKNOWN: _ClassVar[ExtendedSodaConfigMsg.RecognitionMode]
        IME: _ClassVar[ExtendedSodaConfigMsg.RecognitionMode]
        CAPTION: _ClassVar[ExtendedSodaConfigMsg.RecognitionMode]
    UNKNOWN: ExtendedSodaConfigMsg.RecognitionMode
    IME: ExtendedSodaConfigMsg.RecognitionMode
    CAPTION: ExtendedSodaConfigMsg.RecognitionMode
    class SpeakerDiarizationMode(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
        __slots__ = ()
        DIARIZATION_UNSPECIFIED: _ClassVar[ExtendedSodaConfigMsg.SpeakerDiarizationMode]
        SPEAKER_DIARIZATION_MODE_OFF_DEFAULT: _ClassVar[ExtendedSodaConfigMsg.SpeakerDiarizationMode]
        SPEAKER_CHANGE_DETECTION: _ClassVar[ExtendedSodaConfigMsg.SpeakerDiarizationMode]
        SPEAKER_LABEL_DETECTION: _ClassVar[ExtendedSodaConfigMsg.SpeakerDiarizationMode]
    DIARIZATION_UNSPECIFIED: ExtendedSodaConfigMsg.SpeakerDiarizationMode
    SPEAKER_DIARIZATION_MODE_OFF_DEFAULT: ExtendedSodaConfigMsg.SpeakerDiarizationMode
    SPEAKER_CHANGE_DETECTION: ExtendedSodaConfigMsg.SpeakerDiarizationMode
    SPEAKER_LABEL_DETECTION: ExtendedSodaConfigMsg.SpeakerDiarizationMode
    CHANNEL_COUNT_FIELD_NUMBER: _ClassVar[int]
    SAMPLE_RATE_FIELD_NUMBER: _ClassVar[int]
    MAX_BUFFER_BYTES_FIELD_NUMBER: _ClassVar[int]
    SIMULATE_REALTIME_TESTONLY_FIELD_NUMBER: _ClassVar[int]
    CONFIG_FILE_LOCATION_FIELD_NUMBER: _ClassVar[int]
    API_KEY_FIELD_NUMBER: _ClassVar[int]
    LANGUAGE_PACK_DIRECTORY_FIELD_NUMBER: _ClassVar[int]
    RECOGNITION_MODE_FIELD_NUMBER: _ClassVar[int]
    RESET_ON_FINAL_RESULT_FIELD_NUMBER: _ClassVar[int]
    INCLUDE_TIMING_METRICS_FIELD_NUMBER: _ClassVar[int]
    ENABLE_LANG_ID_FIELD_NUMBER: _ClassVar[int]
    ENABLE_FORMATTING_FIELD_NUMBER: _ClassVar[int]
    ENABLE_SPEAKER_CHANGE_DETECTION_FIELD_NUMBER: _ClassVar[int]
    INCLUDE_LOGGING_FIELD_NUMBER: _ClassVar[int]
    MULTILANG_CONFIG_FIELD_NUMBER: _ClassVar[int]
    MASK_OFFENSIVE_WORDS_FIELD_NUMBER: _ClassVar[int]
    SPEAKER_DIARIZATION_MODE_FIELD_NUMBER: _ClassVar[int]
    MAX_SPEAKER_COUNT_FIELD_NUMBER: _ClassVar[int]
    RECOGNITION_CONTEXT_FIELD_NUMBER: _ClassVar[int]
    channel_count: int
    sample_rate: int
    max_buffer_bytes: int
    simulate_realtime_testonly: bool
    config_file_location: str
    api_key: str
    language_pack_directory: str
    recognition_mode: ExtendedSodaConfigMsg.RecognitionMode
    reset_on_final_result: bool
    include_timing_metrics: bool
    enable_lang_id: bool
    enable_formatting: bool
    enable_speaker_change_detection: bool
    include_logging: bool
    multilang_config: MultilangConfig
    mask_offensive_words: bool
    speaker_diarization_mode: ExtendedSodaConfigMsg.SpeakerDiarizationMode
    max_speaker_count: int
    recognition_context: RecognitionContext
    def __init__(self, channel_count: _Optional[int] = ..., sample_rate: _Optional[int] = ..., max_buffer_bytes: _Optional[int] = ..., simulate_realtime_testonly: _Optional[bool] = ..., config_file_location: _Optional[str] = ..., api_key: _Optional[str] = ..., language_pack_directory: _Optional[str] = ..., recognition_mode: _Optional[_Union[ExtendedSodaConfigMsg.RecognitionMode, str]] = ..., reset_on_final_result: _Optional[bool] = ..., include_timing_metrics: _Optional[bool] = ..., enable_lang_id: _Optional[bool] = ..., enable_formatting: _Optional[bool] = ..., enable_speaker_change_detection: _Optional[bool] = ..., include_logging: _Optional[bool] = ..., multilang_config: _Optional[_Union[MultilangConfig, _Mapping]] = ..., mask_offensive_words: _Optional[bool] = ..., speaker_diarization_mode: _Optional[_Union[ExtendedSodaConfigMsg.SpeakerDiarizationMode, str]] = ..., max_speaker_count: _Optional[int] = ..., recognition_context: _Optional[_Union[RecognitionContext, _Mapping]] = ...) -> None: ...

class MultilangConfig(_message.Message):
    __slots__ = ("multilang_language_pack_directory", "rewind_when_switching_language")
    class MultilangLanguagePackDirectoryEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: str
        def __init__(self, key: _Optional[str] = ..., value: _Optional[str] = ...) -> None: ...
    MULTILANG_LANGUAGE_PACK_DIRECTORY_FIELD_NUMBER: _ClassVar[int]
    REWIND_WHEN_SWITCHING_LANGUAGE_FIELD_NUMBER: _ClassVar[int]
    multilang_language_pack_directory: _containers.ScalarMap[str, str]
    rewind_when_switching_language: bool
    def __init__(self, multilang_language_pack_directory: _Optional[_Mapping[str, str]] = ..., rewind_when_switching_language: _Optional[bool] = ...) -> None: ...

class ContextInput(_message.Message):
    __slots__ = ("name", "phrases")
    class Phrase(_message.Message):
        __slots__ = ("phrase", "boost")
        PHRASE_FIELD_NUMBER: _ClassVar[int]
        BOOST_FIELD_NUMBER: _ClassVar[int]
        phrase: str
        boost: float
        def __init__(self, phrase: _Optional[str] = ..., boost: _Optional[float] = ...) -> None: ...
    class Phrases(_message.Message):
        __slots__ = ("phrase",)
        PHRASE_FIELD_NUMBER: _ClassVar[int]
        phrase: _containers.RepeatedCompositeFieldContainer[ContextInput.Phrase]
        def __init__(self, phrase: _Optional[_Iterable[_Union[ContextInput.Phrase, _Mapping]]] = ...) -> None: ...
    NAME_FIELD_NUMBER: _ClassVar[int]
    PHRASES_FIELD_NUMBER: _ClassVar[int]
    name: str
    phrases: ContextInput.Phrases
    def __init__(self, name: _Optional[str] = ..., phrases: _Optional[_Union[ContextInput.Phrases, _Mapping]] = ...) -> None: ...

class RecognitionContext(_message.Message):
    __slots__ = ("context",)
    CONTEXT_FIELD_NUMBER: _ClassVar[int]
    context: _containers.RepeatedCompositeFieldContainer[ContextInput]
    def __init__(self, context: _Optional[_Iterable[_Union[ContextInput, _Mapping]]] = ...) -> None: ...

class TimingMetrics(_message.Message):
    __slots__ = ("audio_start_epoch_usec", "audio_start_time_usec", "elapsed_wall_time_usec", "event_end_time_usec")
    AUDIO_START_EPOCH_USEC_FIELD_NUMBER: _ClassVar[int]
    AUDIO_START_TIME_USEC_FIELD_NUMBER: _ClassVar[int]
    ELAPSED_WALL_TIME_USEC_FIELD_NUMBER: _ClassVar[int]
    EVENT_END_TIME_USEC_FIELD_NUMBER: _ClassVar[int]
    audio_start_epoch_usec: int
    audio_start_time_usec: int
    elapsed_wall_time_usec: int
    event_end_time_usec: int
    def __init__(self, audio_start_epoch_usec: _Optional[int] = ..., audio_start_time_usec: _Optional[int] = ..., elapsed_wall_time_usec: _Optional[int] = ..., event_end_time_usec: _Optional[int] = ...) -> None: ...

class HypothesisPart(_message.Message):
    __slots__ = ("text", "alignment_ms", "speaker_label")
    TEXT_FIELD_NUMBER: _ClassVar[int]
    ALIGNMENT_MS_FIELD_NUMBER: _ClassVar[int]
    SPEAKER_LABEL_FIELD_NUMBER: _ClassVar[int]
    text: _containers.RepeatedScalarFieldContainer[str]
    alignment_ms: int
    speaker_label: int
    def __init__(self, text: _Optional[_Iterable[str]] = ..., alignment_ms: _Optional[int] = ..., speaker_label: _Optional[int] = ...) -> None: ...

class SodaRecognitionResult(_message.Message):
    __slots__ = ("hypothesis", "result_type", "endpoint_reason", "timing_metrics", "hypothesis_part")
    class ResultType(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
        __slots__ = ()
        UNKNOWN: _ClassVar[SodaRecognitionResult.ResultType]
        PARTIAL: _ClassVar[SodaRecognitionResult.ResultType]
        FINAL: _ClassVar[SodaRecognitionResult.ResultType]
        PREFETCH: _ClassVar[SodaRecognitionResult.ResultType]
    UNKNOWN: SodaRecognitionResult.ResultType
    PARTIAL: SodaRecognitionResult.ResultType
    FINAL: SodaRecognitionResult.ResultType
    PREFETCH: SodaRecognitionResult.ResultType
    class FinalResultEndpointReason(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
        __slots__ = ()
        ENDPOINT_UNKNOWN: _ClassVar[SodaRecognitionResult.FinalResultEndpointReason]
        ENDPOINT_END_OF_SPEECH: _ClassVar[SodaRecognitionResult.FinalResultEndpointReason]
        ENDPOINT_END_OF_UTTERANCE: _ClassVar[SodaRecognitionResult.FinalResultEndpointReason]
        ENDPOINT_END_OF_AUDIO: _ClassVar[SodaRecognitionResult.FinalResultEndpointReason]
        ENDPOINT_ASR_RESET_BY_HOTWORD: _ClassVar[SodaRecognitionResult.FinalResultEndpointReason]
        ENDPOINT_ASR_RESET_EXTERNAL: _ClassVar[SodaRecognitionResult.FinalResultEndpointReason]
        ENDPOINT_ASR_ERROR: _ClassVar[SodaRecognitionResult.FinalResultEndpointReason]
    ENDPOINT_UNKNOWN: SodaRecognitionResult.FinalResultEndpointReason
    ENDPOINT_END_OF_SPEECH: SodaRecognitionResult.FinalResultEndpointReason
    ENDPOINT_END_OF_UTTERANCE: SodaRecognitionResult.FinalResultEndpointReason
    ENDPOINT_END_OF_AUDIO: SodaRecognitionResult.FinalResultEndpointReason
    ENDPOINT_ASR_RESET_BY_HOTWORD: SodaRecognitionResult.FinalResultEndpointReason
    ENDPOINT_ASR_RESET_EXTERNAL: SodaRecognitionResult.FinalResultEndpointReason
    ENDPOINT_ASR_ERROR: SodaRecognitionResult.FinalResultEndpointReason
    HYPOTHESIS_FIELD_NUMBER: _ClassVar[int]
    RESULT_TYPE_FIELD_NUMBER: _ClassVar[int]
    ENDPOINT_REASON_FIELD_NUMBER: _ClassVar[int]
    TIMING_METRICS_FIELD_NUMBER: _ClassVar[int]
    HYPOTHESIS_PART_FIELD_NUMBER: _ClassVar[int]
    hypothesis: _containers.RepeatedScalarFieldContainer[str]
    result_type: SodaRecognitionResult.ResultType
    endpoint_reason: SodaRecognitionResult.FinalResultEndpointReason
    timing_metrics: TimingMetrics
    hypothesis_part: _containers.RepeatedCompositeFieldContainer[HypothesisPart]
    def __init__(self, hypothesis: _Optional[_Iterable[str]] = ..., result_type: _Optional[_Union[SodaRecognitionResult.ResultType, str]] = ..., endpoint_reason: _Optional[_Union[SodaRecognitionResult.FinalResultEndpointReason, str]] = ..., timing_metrics: _Optional[_Union[TimingMetrics, _Mapping]] = ..., hypothesis_part: _Optional[_Iterable[_Union[HypothesisPart, _Mapping]]] = ...) -> None: ...

class SodaEndpointEvent(_message.Message):
    __slots__ = ("endpoint_type", "timing_metrics")
    class EndpointType(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
        __slots__ = ()
        START_OF_SPEECH: _ClassVar[SodaEndpointEvent.EndpointType]
        END_OF_SPEECH: _ClassVar[SodaEndpointEvent.EndpointType]
        END_OF_AUDIO: _ClassVar[SodaEndpointEvent.EndpointType]
        END_OF_UTTERANCE: _ClassVar[SodaEndpointEvent.EndpointType]
        UNKNOWN: _ClassVar[SodaEndpointEvent.EndpointType]
    START_OF_SPEECH: SodaEndpointEvent.EndpointType
    END_OF_SPEECH: SodaEndpointEvent.EndpointType
    END_OF_AUDIO: SodaEndpointEvent.EndpointType
    END_OF_UTTERANCE: SodaEndpointEvent.EndpointType
    UNKNOWN: SodaEndpointEvent.EndpointType
    ENDPOINT_TYPE_FIELD_NUMBER: _ClassVar[int]
    TIMING_METRICS_FIELD_NUMBER: _ClassVar[int]
    endpoint_type: SodaEndpointEvent.EndpointType
    timing_metrics: TimingMetrics
    def __init__(self, endpoint_type: _Optional[_Union[SodaEndpointEvent.EndpointType, str]] = ..., timing_metrics: _Optional[_Union[TimingMetrics, _Mapping]] = ...) -> None: ...

class SodaAudioLevelInfo(_message.Message):
    __slots__ = ("rms", "audio_level", "audio_time_usec")
    RMS_FIELD_NUMBER: _ClassVar[int]
    AUDIO_LEVEL_FIELD_NUMBER: _ClassVar[int]
    AUDIO_TIME_USEC_FIELD_NUMBER: _ClassVar[int]
    rms: float
    audio_level: float
    audio_time_usec: int
    def __init__(self, rms: _Optional[float] = ..., audio_level: _Optional[float] = ..., audio_time_usec: _Optional[int] = ...) -> None: ...

class SodaLangIdEvent(_message.Message):
    __slots__ = ("language", "confidence_level", "asr_switch_result")
    class AsrSwitchResult(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
        __slots__ = ()
        DEFAULT_NO_SWITCH: _ClassVar[SodaLangIdEvent.AsrSwitchResult]
        SWITCH_SUCCEEDED: _ClassVar[SodaLangIdEvent.AsrSwitchResult]
        SWITCH_FAILED: _ClassVar[SodaLangIdEvent.AsrSwitchResult]
        SWITCH_SKIPPED_NO_LP: _ClassVar[SodaLangIdEvent.AsrSwitchResult]
    DEFAULT_NO_SWITCH: SodaLangIdEvent.AsrSwitchResult
    SWITCH_SUCCEEDED: SodaLangIdEvent.AsrSwitchResult
    SWITCH_FAILED: SodaLangIdEvent.AsrSwitchResult
    SWITCH_SKIPPED_NO_LP: SodaLangIdEvent.AsrSwitchResult
    LANGUAGE_FIELD_NUMBER: _ClassVar[int]
    CONFIDENCE_LEVEL_FIELD_NUMBER: _ClassVar[int]
    ASR_SWITCH_RESULT_FIELD_NUMBER: _ClassVar[int]
    language: str
    confidence_level: int
    asr_switch_result: SodaLangIdEvent.AsrSwitchResult
    def __init__(self, language: _Optional[str] = ..., confidence_level: _Optional[int] = ..., asr_switch_result: _Optional[_Union[SodaLangIdEvent.AsrSwitchResult, str]] = ...) -> None: ...

class SodaResponse(_message.Message):
    __slots__ = ("soda_type", "recognition_result", "endpoint_event", "audio_level_info", "langid_event", "log_lines")
    class SodaMessageType(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
        __slots__ = ()
        UNKNOWN: _ClassVar[SodaResponse.SodaMessageType]
        RECOGNITION: _ClassVar[SodaResponse.SodaMessageType]
        STOP: _ClassVar[SodaResponse.SodaMessageType]
        SHUTDOWN: _ClassVar[SodaResponse.SodaMessageType]
        START: _ClassVar[SodaResponse.SodaMessageType]
        ENDPOINT: _ClassVar[SodaResponse.SodaMessageType]
        AUDIO_LEVEL: _ClassVar[SodaResponse.SodaMessageType]
        LANGID: _ClassVar[SodaResponse.SodaMessageType]
        LOGS_ONLY_ARTIFICIAL_MESSAGE: _ClassVar[SodaResponse.SodaMessageType]
    UNKNOWN: SodaResponse.SodaMessageType
    RECOGNITION: SodaResponse.SodaMessageType
    STOP: SodaResponse.SodaMessageType
    SHUTDOWN: SodaResponse.SodaMessageType
    START: SodaResponse.SodaMessageType
    ENDPOINT: SodaResponse.SodaMessageType
    AUDIO_LEVEL: SodaResponse.SodaMessageType
    LANGID: SodaResponse.SodaMessageType
    LOGS_ONLY_ARTIFICIAL_MESSAGE: SodaResponse.SodaMessageType
    SODA_TYPE_FIELD_NUMBER: _ClassVar[int]
    RECOGNITION_RESULT_FIELD_NUMBER: _ClassVar[int]
    ENDPOINT_EVENT_FIELD_NUMBER: _ClassVar[int]
    AUDIO_LEVEL_INFO_FIELD_NUMBER: _ClassVar[int]
    LANGID_EVENT_FIELD_NUMBER: _ClassVar[int]
    LOG_LINES_FIELD_NUMBER: _ClassVar[int]
    soda_type: SodaResponse.SodaMessageType
    recognition_result: SodaRecognitionResult
    endpoint_event: SodaEndpointEvent
    audio_level_info: SodaAudioLevelInfo
    langid_event: SodaLangIdEvent
    log_lines: _containers.RepeatedScalarFieldContainer[str]
    def __init__(self, soda_type: _Optional[_Union[SodaResponse.SodaMessageType, str]] = ..., recognition_result: _Optional[_Union[SodaRecognitionResult, _Mapping]] = ..., endpoint_event: _Optional[_Union[SodaEndpointEvent, _Mapping]] = ..., audio_level_info: _Optional[_Union[SodaAudioLevelInfo, _Mapping]] = ..., langid_event: _Optional[_Union[SodaLangIdEvent, _Mapping]] = ..., log_lines: _Optional[_Iterable[str]] = ...) -> None: ...
