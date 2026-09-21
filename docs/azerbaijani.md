# Dictating Azerbaijani

Azerbaijani is one of the languages Dikte offers under **Settings → General →
Speech language**. What follows is what the setting changes, and what it cannot
change.

## What picking it does

* `language=az` is sent with every transcription request. Whisper carries
  Azerbaijani in its own language table (`az`, id 45 in whisper.cpp), so this is
  a real language for the model rather than a hint.
* The cleanup, subtitle, minutes and agent prompts switch to their Azerbaijani
  versions. They follow the **spoken** language, not the interface language, so
  an English or Turkish window still gets the Azerbaijani prompt.
* The two sides of a meeting are labelled `Mən` and `Qarşı tərəf` unless you
  named them yourself.
* Stock phrases in Azerbaijani are recognised by the silence filter, which
  needed a fold of its own: `ə` survives Unicode decomposition, so it is folded
  to `e` by hand alongside `ı`, `ş` and `ğ`. `İzlədiyiniz üçün təşəkkürlər` is
  in that list because large-v3 really did return it, twice, for audio holding
  no speech.
* The cleanup prompt removes a stock phrase that arrived stuck to the front of a
  real sentence, which the silence filter cannot: it only drops a transcript
  that is nothing but the phrase. Measured over ten runs on the same transcript,
  the prompt without that rule left the phrase in 10 times out of 10, and with
  it removed the phrase 10 times out of 10.

## Why the prompt is not the Turkish one with a few words swapped

The Turkish cleanup prompt lists `hani`, `yani`, `işte`, `şey`, `falan` and `ya`
as filler to delete. Run over Azerbaijani, that sweep takes `də`/`da` with it,
which is not filler but a particle that carries meaning: *mən **də** gəldim* is
not *mən gəldim*. The Azerbaijani prompt lists Azerbaijani filler (`yəni`,
`elə`, `bax`, `hə`, `filan`) and protects `də`/`da`, `ki`, `isə` explicitly.

It also carries one repair the other prompts do not: transcription models
frequently write Azerbaijani in Turkish orthography (`çok`, `değil`, `olacak`),
and the prompt asks for those to be brought back to the Azerbaijani norm
(`çox`, `deyil`, `olacaq`). This is a spelling correction only — the prompt is
explicit that a word must not be swapped for another one, and that the text must
not be translated.

## Choose the model deliberately

Azerbaijani is a low-resource language for Whisper, and the difference between
model sizes is much larger than it is for Turkish. Measured on FLEURS-az
(n=923) and Common Voice 25 az:

| Model | FLEURS-az WER | CV25-az WER |
| --- | --- | --- |
| Whisper large-v3 | 21.7% | 26.5% |
| MMS-1B (azj-latin) | 23.8% | 28.3% |
| Whisper medium | 34.3% | 42.1% |
| Whisper small | 51.7% | 62.8% |
| Whisper base | 82.1% | — |

Source: <https://github.com/mammadovziya/whisper-az>

Two things follow from that table.

**Do not leave it on `large-v3-turbo`.** It is what Settings offers first,
because it is the right default for the languages Dikte was written for. Turbo
keeps large-v3's encoder but cuts the decoder from 32 layers to 4, and OpenAI's
own comparison for it covers only the languages where large-v3 scored 20% error
or lower — Azerbaijani, at 21.7%, is outside that set and was never published.
Pick `ggml-large-v3.bin` under Settings → API and models, or send the audio to
Groq (`whisper-large-v3`) or OpenAI (`gpt-4o-transcribe`) instead.

**Check whether the machine can carry `large-v3` at all before committing
to it.** Which build of whisper runs is decided by `_wanted_assets` and
`_managed_whisper` in `dikte/ggml.py`:

- **Linux x86_64 with a Vulkan loader:** a Vulkan whisper-server Dikte builds
  itself (release `whisper.cpp-v1.9.3`, taken only when its SHA-256 is the
  reviewed one), so the graphics card does the work. Without a Vulkan loader,
  on ARM, or when that download is not there, it is whisper.cpp's CPU build.
- **Windows:** always the CPU. The OpenBLAS build `whisper-blas-bin-x64.zip`
  first, the stock `whisper-bin-x64.zip` after it; the CUDA archives are never
  picked, whatever the graphics card, and an ARM machine runs the x64 build
  emulated.

The measurement below was taken on Linux with the CPU build, before the
Vulkan one existed, so it describes a Linux machine left on the CPU. Windows
runs the OpenBLAS build instead, which has not been measured here.
Measured on an i7-1165G7 (4 cores, 15 W) with `ggml-large-v3-q5_0.bin` and the
icelake CPU backend:

```
encode time = 56678 ms / 1 run     <- 93% of the time
decode time =  1730 ms / 19 runs
total time  = 60888 ms
```

Two things follow. A five-second clip and a ten-second one both cost about a
minute, because whisper pads every clip to a 30-second window and the encoder
cost is per window rather than per second. And `large-v3-turbo` does not help:
it keeps the same 32-layer encoder and only cuts the decoder from 32 layers to
4, which is the 3% of the time that was never the problem. On a machine like
that, send the audio to Groq (`whisper-large-v3`, the same model as the table
above) rather than reaching for a smaller local one, whose Azerbaijani error
rate makes it not worth the wait it saves.

**Do not leave the language on `Detect automatically`.** Whisper routinely
detects Azerbaijani speech as Turkish, which is the failure the benchmark above
calls out by name. Naming the language is what stops it — and naming it is not
always enough, which is the next section.

## On Windows

Everything above holds there too: the language list, the prompts, the silence
check. What differs is around them.

- **The settings start empty.** They live in `%APPDATA%\Dikte`, models and
  recordings in `%LOCALAPPDATA%\Dikte`, so nothing set on Linux comes along:
  pick Azerbaijani, the provider and its key again.
- **Pick the microphone by name.** Windows records through ffmpeg's dshow,
  which has no default device; with the setting left empty Dikte takes the
  first one ffmpeg lists (`_dshow_first_device` in `dikte/audio.py`), and a
  headset's is not necessarily that one. `dikte devices` lists them.
- **Local whisper runs on the CPU** (see above). The OpenBLAS build is about
  twice as fast as the stock one by `README.windows.md`, but it has not been
  measured with `large-v3` here; Groq, OpenAI or OpenRouter is the way to it
  that does not depend on the machine.
- **Install this branch from a checkout**, with `install.ps1`. The setup on
  upstream's releases page is built without Azerbaijani, and installing it
  replaces this one. The update notice looks at this fork for that reason
  (`REPO` in `dikte/update.py`).

## Whisper is not the best model here

The benchmark above is a Whisper benchmark: it compares Whisper sizes against
MMS and says nothing about anything else. Run against six recordings of the same
Azerbaijani sentence, spoken into a laptop microphone with the language set to
`az`, the picture changes. The measure that matters is not only how many words
land but whether the model stays in Azerbaijani at all:

| Model (via OpenRouter) | "Kubernetes" heard | drifted into Turkish | latency |
| --- | --- | --- | --- |
| `openai/gpt-4o-transcribe` | 3/6 | **0/6** | 1.4 s |
| `google/chirp-3` | 5/6 | 2/6, fully | 3.7 s |
| `openai/whisper-large-v3` | 2/6 | 2/6, partly | 2.7 s |
| `openai/gpt-4o-mini-transcribe` | 1/6 | 0/6 | 1.3 s |
| `openai/whisper-large-v3-turbo` | 0/6 | — | 2.3 s |

`chirp-3` hears the words best and is still the wrong choice: twice it returned
the sentence in Turkish outright, down to the Turkish apostrophe in
`Grafana'da`. `gpt-4o-transcribe` never left Azerbaijani in any of the six, and
is the fastest of them. That is the one to pick.

`mistralai/voxtral-mini-transcribe` and `deepgram/nova-3` both answer HTTP 400
to the request Dikte sends, and are not usable from here at all.

## The glossary does not reach the transcription model on OpenRouter

`api.py` deliberately drops the `prompt` field for OpenRouter, and a measurement
confirms the comment is still true: eighteen requests with the hint and eighteen
without recognised "Kubernetes" 9 times each and "Grafana" 12 times each —
identical. On Azerbaijani, where proper nouns are the dominant failure, that is
the one hint worth having, so a glossary that has to reach the transcription
model means going to OpenAI or Groq directly rather than through OpenRouter.
Through OpenRouter the glossary still works, but only at the cleanup stage.

## What is still worse than Turkish

Even at its best, a 21.7% word error rate is roughly two to three times the rate
Whisper large-v3 reaches on Turkish. No prompt fixes that: the cleanup model can
repair a word the context settles, but it cannot recover one that was never
heard. The glossary under **Settings → Cleanup rules** is the one lever that
helps measurably — the names and terms listed there go to the transcription
model as a hint and to the cleanup model as a spelling list, which is where most
of the remaining errors are.
