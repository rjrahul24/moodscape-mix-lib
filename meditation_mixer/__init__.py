"""meditation_mixer — studio-grade meditation and sleep story audio from a script.

Renders ElevenLabs v3 narration mixed with a background track through a
broadcast-quality DSP pipeline: frequency-selective sidechain ducking,
convolution reverb, LUFS-normalized mastering with true-peak limiting.

Key entry points:
    mixer.render()              End-to-end mix pipeline
    mixer.MixSettings           All tuned DSP defaults (dataclass)
    tts.synthesize_script()     Script -> narrated audio + manifest
    chunker.chunk_script()      Script -> SpeechChunk / PauseChunk list
    presets.PRESETS              Content type registry (Meditation, Sleep Story)
    cache.clear()               Wipe the TTS disk cache
"""
