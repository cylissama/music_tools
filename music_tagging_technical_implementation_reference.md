# Technical Reference: Modern Music Tagging Implementation

**Purpose:** This document is written as an implementation reference for another LLM or developer agent that needs to build a modern music tagging system. It focuses on how to read music files, normalize metadata, infer missing tags, apply best-practice tag logic, and safely write tags back to audio files.

**Target system:** A local or server-side music tagger that can handle mixed audio libraries, including MP3, FLAC, OGG/Opus, M4A/MP4, WAV, AIFF, and related formats.

---

## 1. Core Definitions

### 1.1 Metadata tagging vs. audio-content tagging

A complete music tagging system should separate two different tasks:

1. **Metadata tagging**
   - Reads or writes file metadata fields such as title, artist, album, album artist, track number, disc number, date, genre, composer, ISRC, MusicBrainz IDs, and artwork.
   - Uses file containers and tag standards such as ID3, Vorbis Comments, MP4 atoms, ASF tags, and APEv2.
   - Can use sources such as MusicBrainz, Discogs, AcoustID, existing filenames, and user-provided rules.

2. **Audio-content tagging**
   - Listens to the audio signal and predicts descriptive attributes.
   - Common outputs include genre, mood, instrument, vocal/instrumental, tempo, key, energy, danceability, acoustic/electronic, speech/music, and similarity embeddings.
   - Usually implemented as a machine learning pipeline using spectrograms, audio embeddings, pretrained transformers, CNNs, or audio foundation models.

A well-designed application should not treat these as the same. Metadata tagging answers “what release is this file?” Audio-content tagging answers “what does this track sound like?”

---

## 2. Recommended System Architecture

Use a staged pipeline. Each stage should produce structured intermediate output and confidence scores.

```text
Input audio files
    ↓
File discovery and validation
    ↓
Metadata read layer
    ↓
Audio fingerprinting and external metadata lookup
    ↓
Audio feature extraction
    ↓
ML inference for descriptive tags
    ↓
Tag normalization and controlled vocabulary mapping
    ↓
Conflict resolution and confidence scoring
    ↓
Human review queue, optional
    ↓
Safe write-back to file tags
    ↓
Audit log and rollback manifest
```

### 2.1 Recommended modules

```text
music_tagger/
  config/
    tag_schema.yaml
    vocabulary.yaml
    field_mapping.yaml
    model_config.yaml
  ingest/
    scanner.py
    validators.py
  metadata/
    reader.py
    writer.py
    mappings.py
    artwork.py
  lookup/
    acoustid_client.py
    musicbrainz_client.py
    discogs_client.py
  audio/
    decode.py
    preprocess.py
    features.py
    embeddings.py
  models/
    genre_model.py
    mood_model.py
    instrument_model.py
    chain_decoder.py
    calibrate.py
  rules/
    normalize.py
    conflict_resolution.py
    thresholds.py
  review/
    reports.py
    diffs.py
  cli.py
```

---

## 3. File and Metadata Handling

### 3.1 Use a format-aware metadata library

For Python implementations, use **Mutagen** as the first choice for local metadata read/write. It supports many audio formats, including MP3, FLAC, MP4, Ogg, Opus, WavPack, AIFF, and ASF. It also supports ID3v2 versions and common audio metadata operations.

Recommended package:

```bash
pip install mutagen
```

Use separate writer logic per container because the same conceptual field maps to different physical tag keys depending on format.

### 3.2 Format-specific tag standards

| File type | Preferred tag system | Notes |
|---|---|---|
| MP3 | ID3v2.3 or ID3v2.4 | ID3v2.3 is often more compatible with older software. ID3v2.4 is more modern but can cause compatibility issues in some players. |
| FLAC | Vorbis Comments | Do not write ID3 tags into FLAC unless you have a very specific compatibility reason. |
| OGG / Opus | Vorbis Comments / Opus tags | Store text fields as UTF-8. |
| M4A / MP4 | MP4 atoms | Field names differ strongly from ID3. |
| WAV | RIFF INFO or ID3 chunks | WAV tagging is less consistent across players. Consider sidecar JSON for advanced metadata. |
| AIFF | ID3 or AIFF metadata chunks | Test compatibility with the target player. |

### 3.3 Canonical internal metadata model

Do not let each file format control the internal data model. Convert every file’s metadata into a canonical object, then write format-specific mappings at the output stage.

```json
{
  "file_path": "/music/Artist/Album/01 - Track.flac",
  "format": "FLAC",
  "duration_sec": 213.4,
  "audio_hash": "sha256:...",
  "metadata": {
    "title": "Track Title",
    "artist": ["Artist Name"],
    "album": "Album Title",
    "album_artist": ["Album Artist"],
    "track_number": 1,
    "track_total": 12,
    "disc_number": 1,
    "disc_total": 1,
    "date": "2024",
    "original_date": null,
    "genre": ["Alternative Rock"],
    "composer": [],
    "isrc": null,
    "musicbrainz_recording_id": null,
    "musicbrainz_release_id": null,
    "musicbrainz_artist_id": []
  },
  "content_tags": {
    "mood": [],
    "instrument": [],
    "energy": null,
    "bpm": null,
    "key": null,
    "vocal_presence": null
  },
  "artwork": {
    "embedded": false,
    "external_path": "folder.jpg"
  }
}
```

---

## 4. Logical Tagging Best Practices

### 4.1 Use a controlled vocabulary

The biggest long-term mistake in tagging systems is uncontrolled free text. Avoid ending up with all of these as separate values:

```text
Hip Hop
Hip-Hop
hiphop
Hip hop
Rap/Hip-Hop
```

Define canonical tags and aliases:

```yaml
genres:
  hip_hop:
    display: "Hip-Hop"
    aliases: ["hip hop", "hiphop", "rap/hip-hop", "rap hip hop"]
  r_and_b:
    display: "R&B"
    aliases: ["rnb", "rhythm and blues", "r & b"]

moods:
  energetic:
    display: "Energetic"
    aliases: ["high energy", "upbeat", "driving"]
  melancholic:
    display: "Melancholic"
    aliases: ["sad", "somber", "blue"]
```

### 4.2 Separate factual metadata from interpretive tags

Factual metadata should be treated differently from subjective tags.

| Type | Examples | Handling |
|---|---|---|
| Factual metadata | title, artist, album, track number, disc number, ISRC, MusicBrainz IDs | Prefer authoritative sources. Do not overwrite without high confidence. |
| Semi-factual descriptors | BPM, key, release date, original date | Can be estimated, but store confidence and method. |
| Interpretive descriptors | mood, energy, genre, theme, vibe | Allow multi-label predictions and human correction. |
| Workflow tags | needs_review, low_confidence, duplicate_candidate | Store internally or in sidecar, not necessarily in the audio file. |

### 4.3 Keep album-level and track-level tags separate

Some fields must be identical for every track on an album:

- `album`
- `album_artist`
- `date` or `original_date`
- `disc_total`
- `compilation`
- `musicbrainz_release_id`
- album artwork

Some fields are track-specific:

- `title`
- `artist`, especially for features and collaborations
- `track_number`
- `isrc`
- `bpm`
- `key`
- `mood`
- `energy`
- `lyrics`
- `musicbrainz_recording_id`

Implement an album consistency validator:

```python
def validate_album_consistency(tracks):
    album_fields = ["album", "album_artist", "date", "disc_total"]
    issues = []
    for field in album_fields:
        values = {track.metadata.get(field) for track in tracks}
        if len(values) > 1:
            issues.append({
                "field": field,
                "values": list(values),
                "severity": "warning"
            })
    return issues
```

### 4.4 Preserve original metadata before overwriting

Before writing changes, store a JSON snapshot:

```json
{
  "file": "/music/example.flac",
  "timestamp": "2026-04-30T18:00:00Z",
  "before": {
    "title": "Old Title",
    "artist": "Old Artist"
  },
  "after": {
    "title": "New Title",
    "artist": "Correct Artist"
  },
  "source": {
    "musicbrainz": true,
    "acoustid": true,
    "ml_inference": false,
    "manual_review": true
  }
}
```

### 4.5 Never blindly clear all tags

Some taggers support clearing existing tags before writing new metadata. This can be useful for cleanup, but it can also delete custom genre, comments, ratings, mood tags, DJ cues, ReplayGain, or user-defined fields. Implement allowlists and preserve lists.

Recommended default:

```yaml
write_policy:
  clear_existing_tags: false
  preserve_fields:
    - rating
    - comment
    - grouping
    - replaygain_track_gain
    - replaygain_album_gain
    - bpm
    - initial_key
    - mood
    - custom:*
```

---

## 5. External Metadata Lookup

### 5.1 MusicBrainz and AcoustID

Use **MusicBrainz** for release metadata and **AcoustID** for fingerprint-based identification.

Recommended lookup order:

```text
1. Try embedded MusicBrainz IDs.
2. If missing, parse filename and directory context.
3. Generate AcoustID fingerprint.
4. Query AcoustID for candidate recordings.
5. Query MusicBrainz for full recording/release metadata.
6. Score candidate releases using album context.
7. Apply only high-confidence matches automatically.
8. Send ambiguous matches to review.
```

### 5.2 Candidate scoring

Use weighted scoring. Do not rely on one signal.

```python
score = (
    0.40 * acoustid_confidence +
    0.20 * title_similarity +
    0.15 * artist_similarity +
    0.10 * album_similarity +
    0.05 * duration_similarity +
    0.05 * track_number_match +
    0.05 * directory_context_match
)
```

Suggested thresholds:

| Score | Action |
|---:|---|
| >= 0.90 | Auto-apply factual metadata. |
| 0.75–0.89 | Apply only safe fields or require review. |
| 0.50–0.74 | Add to review queue. |
| < 0.50 | Do not apply. |

### 5.3 Album-oriented matching

For albums, match groups of files together rather than each track independently. Album-oriented matching reduces incorrect release choices, especially for remasters, deluxe editions, compilations, and live releases.

Use directory context:

```text
/Artist/Album/01 - Title.flac
/Artist/Album/02 - Title.flac
```

Infer album candidate by checking:

- number of tracks
- track durations
- track order
- album title similarity
- album artist similarity
- release country and date preferences
- disc count
- file count per disc

---

## 6. Audio Preprocessing for ML Tagging

### 6.1 Decode policy

Standardize decoding before inference.

Recommended defaults:

```yaml
audio_decode:
  sample_rate: 16000 or 32000
  channels: mono
  normalize_peak: false
  loudness_normalization: optional
  trim_silence: false for full-track tagging
  max_duration_sec: null
```

For transformer and CNN taggers, use the sample rate expected by the model. Many audio models expect 16 kHz or 32 kHz.

### 6.2 Segmenting strategy

Full tracks are long, but many models are trained on 5–30 second clips. Use segment-level inference and aggregate.

Recommended approach:

```text
1. Load full audio.
2. Select N clips:
   - intro-safe clip after 10–20 seconds
   - middle clip
   - late-middle clip
   - optionally 8 evenly spaced clips
3. Run model on each clip.
4. Aggregate probabilities by mean, max, or calibrated weighted mean.
5. Store clip-level predictions for explainability.
```

Example:

```python
def select_clips(duration, clip_len=10.0, n=8):
    if duration <= clip_len:
        return [(0.0, duration)]
    max_start = duration - clip_len
    return [(i * max_start / max(n - 1, 1), clip_len) for i in range(n)]
```

### 6.3 Spectrogram features

Common ML inputs:

| Feature | Use case |
|---|---|
| Mel spectrogram | Default for CNNs and audio transformers. |
| Log-mel spectrogram | Most common for deep learning. |
| MFCC | Lightweight genre/mood models and classical ML. |
| STFT magnitude | CNNs or spectrogram ensembles. |
| Chroma / HPCP | Key, harmony, tonal similarity. |
| Onset / beat features | Tempo, rhythm, danceability. |
| Wavelet features | Some genre systems combine DWT with CNNs. |

Baseline mel config:

```yaml
mel:
  sample_rate: 16000
  n_fft: 1024
  hop_length: 160
  win_length: 400
  n_mels: 128
  f_min: 0
  f_max: 8000
  power: 2.0
  log_scale: true
```

---

## 7. Modern ML Techniques for Music Tagging

### 7.1 Multi-label classification baseline

Music tagging is usually **multi-label**, not single-label. A track can be tagged as:

```text
genre: pop, electronic
mood: energetic, happy
instrument: synth, drums, bass
```

The standard baseline is:

```text
audio → encoder → latent vector → linear layer → sigmoid probabilities
```

Use sigmoid outputs, not softmax, because multiple labels can be true simultaneously.

Loss function:

```python
loss = BCEWithLogitsLoss(pos_weight=class_weights)
```

Evaluation metrics:

- ROC-AUC
- PR-AUC
- macro/micro F1
- precision@k
- recall@k
- calibration error
- per-category metrics

### 7.2 CNN-based methods

CNN systems often operate on spectrograms as images.

Implementation options:

```text
audio → log-mel spectrogram → CNN → dense layer → sigmoid tags
```

Pros:

- relatively easy to train
- efficient inference
- strong baseline for genre classification
- works well with moderate datasets

Cons:

- less capable at long-range temporal context than transformers
- may overfit small datasets
- needs careful augmentation

Recommended augmentations:

```yaml
augmentation:
  random_crop: true
  time_masking: true
  frequency_masking: true
  mixup: optional
  gain_augmentation_db: [-6, 6]
  background_noise: optional
```

### 7.3 Parallel feature CNN ensembles

One uploaded 2025 paper proposes a genre-classification approach using multiple feature streams: DWT, MFCC, and STFT, with CNN models optimized by the Capuchin Search Algorithm. The system has four major components: preprocessing, feature description with DWT/MFCC/STFT matrices, CNN optimization, and final genre identification from combined features. This is useful as a reference for a feature-ensemble architecture, but it is more specialized for genre classification than broad tagging.

Implementation pattern:

```text
audio
  ├── MFCC matrix → CNN branch ┐
  ├── STFT matrix → CNN branch ├── concatenate → classifier
  └── DWT matrix  → CNN branch ┘
```

Use this when:

- the target task is mostly genre classification
- you need interpretable signal-processing branches
- compute budget allows multiple feature extractors
- you have enough labeled data

Avoid treating this as the only “state of the art” approach for broad tagging. Modern production systems often use pretrained encoders and embeddings.

### 7.4 Transformer-based audio encoders

Modern audio tagging often uses pretrained transformer encoders over waveforms or spectrogram patches.

Useful encoder families:

| Model family | Input | Notes |
|---|---|---|
| PaSST | spectrogram patches | Efficient spectrogram transformer; strong for AudioSet-style tagging. |
| HTS-AT | spectrogram/token hierarchy | Hierarchical token-semantic transformer for classification and localization. |
| AST | spectrogram patches | Audio Spectrogram Transformer; ViT-style. |
| BEATs | acoustic tokens | General audio pretraining. |
| MERT / music-specific encoders | waveform/audio | Music-focused representations; useful for downstream MIR. |
| CLAP / audio-text models | audio + text embeddings | Useful for zero-shot or text-query tagging. |

Recommended default for an implementation-focused system:

```text
Use a pretrained encoder first.
Freeze encoder initially.
Train small task-specific heads.
Only fine-tune encoder after baseline is stable.
```

### 7.5 Classifier group chains

The uploaded “Music Tagging with Classifier Group Chains” paper argues that conventional taggers often estimate tags independently and therefore miss dependencies among tag groups. It proposes grouping tags by category, such as genre, instrument, and mood/theme, and estimating groups sequentially with a chain decoder.

Conventional independent model:

```text
z = encoder(audio)
genre_i = sigmoid(linear_i(z))
mood_j = sigmoid(linear_j(z))
instrument_k = sigmoid(linear_k(z))
```

Classifier group chain model:

```text
z = encoder(audio)

genre_probs = decoder_genre(z)

instrument_probs = decoder_instrument(
    z,
    previous_predictions=genre_probs
)

mood_probs = decoder_mood(
    z,
    previous_predictions=[genre_probs, instrument_probs]
)
```

General implementation:

```python
class ClassifierGroupChain(nn.Module):
    def __init__(self, z_dim, group_sizes, hidden_size=128):
        super().__init__()
        self.group_sizes = group_sizes
        self.total_tags = sum(group_sizes)
        self.gru = nn.GRU(
            input_size=z_dim + self.total_tags,
            hidden_size=hidden_size,
            num_layers=1,
            batch_first=True
        )
        self.heads = nn.ModuleList([
            nn.Linear(hidden_size, size) for size in group_sizes
        ])
        self.h0 = nn.Parameter(torch.zeros(1, 1, hidden_size))

    def forward(self, z):
        batch = z.shape[0]
        previous = torch.zeros(batch, self.total_tags, device=z.device)
        hidden = self.h0.repeat(1, batch, 1)
        outputs = []

        offset = 0
        for group_idx, group_size in enumerate(self.group_sizes):
            x = torch.cat([z, previous], dim=-1).unsqueeze(1)
            out, hidden = self.gru(x, hidden)
            logits = self.heads[group_idx](out.squeeze(1))
            probs = torch.sigmoid(logits)

            previous[:, offset:offset + group_size] = probs.detach()
            outputs.append(logits)
            offset += group_size

        return torch.cat(outputs, dim=-1)
```

Important implementation detail:

- During training, consider teacher forcing using ground-truth previous group labels.
- During inference, use predicted probabilities.
- Compare both variants because teacher forcing can cause train/inference mismatch.
- Evaluate different group orders:
  - `genre → instrument → mood`
  - `instrument → genre → mood`
  - `mood → genre → instrument`

Recommended group ordering:

```text
Start with genre → instrument → mood/theme as a reasonable default.
Then run ablation tests.
Do not assume the best order is universal.
```

### 7.6 Zero-shot and text-guided tagging

Audio-text embedding models such as CLAP-style systems can map audio and text prompts into a shared embedding space. This enables prompt-based tagging:

```text
audio embedding ≈ "an energetic punk rock song with distorted guitar"
audio embedding ≈ "slow ambient instrumental music"
```

Use zero-shot tagging for:

- bootstrapping labels
- user-defined tags
- search and discovery
- low-data categories
- generating candidates for human review

Do not use zero-shot predictions as authoritative file metadata without confidence thresholds and review. They are useful as suggestions.

---

## 8. Hybrid Tagging Strategy

The best practical system is hybrid:

```text
Factual metadata:
    MusicBrainz / Discogs / AcoustID / filename parsing

Descriptive metadata:
    ML inference + controlled vocabulary

Musical attributes:
    DSP algorithms + ML correction
```

### 8.1 Recommended strategy by field

| Field | Preferred source | Fallback |
|---|---|---|
| title | MusicBrainz release match | filename parsing |
| artist | MusicBrainz release match | existing tag |
| album | MusicBrainz release match | directory name |
| album_artist | MusicBrainz release match | existing tag |
| track number | MusicBrainz release match | filename prefix |
| disc number | MusicBrainz release match | directory pattern |
| ISRC | MusicBrainz / Discogs | preserve existing |
| genre | controlled vocabulary + MusicBrainz/Discogs + ML | existing tag |
| mood | ML classifier | zero-shot audio-text model |
| instrument | ML classifier | zero-shot model |
| BPM | beat tracking algorithm | existing tag |
| key | key detection algorithm | existing tag |
| artwork | Cover Art Archive / existing folder art | embedded existing art |

---

## 9. Confidence and Conflict Resolution

### 9.1 Track confidence per field

Every proposed tag should carry:

```json
{
  "field": "genre",
  "value": "Synthpop",
  "confidence": 0.86,
  "source": "ml_model:v1.2.0",
  "method": "multi_label_classifier",
  "timestamp": "2026-04-30T18:00:00Z"
}
```

### 9.2 Resolve conflicts by field type

Factual fields:

```text
authoritative database > embedded MusicBrainz ID > high-confidence fingerprint > filename parse > existing tag
```

Descriptive fields:

```text
manual user tag > curated source > calibrated ML model > zero-shot suggestion > existing unknown tag
```

### 9.3 Use field-specific thresholds

```yaml
thresholds:
  genre:
    auto_apply: 0.80
    suggest: 0.45
    max_tags: 3
  mood:
    auto_apply: 0.75
    suggest: 0.40
    max_tags: 5
  instrument:
    auto_apply: 0.70
    suggest: 0.35
    max_tags: 6
  explicit:
    auto_apply: never
```

### 9.4 Calibrate model probabilities

Raw sigmoid outputs are not always calibrated. Use validation data to calibrate thresholds.

Options:

- temperature scaling
- Platt scaling
- isotonic regression
- per-tag threshold search
- precision-targeted thresholds

Recommended:

```text
For each tag, choose threshold that reaches desired precision on validation set.
For user-facing auto-write, prefer high precision over high recall.
```

---

## 10. Model Training Reference

### 10.1 Dataset choices

Useful datasets for training/evaluation:

| Dataset | Use |
|---|---|
| MTG-Jamendo | Multi-label music tagging with genre/instrument/mood categories. |
| MagnaTagATune | Classic multi-label music tagging dataset. |
| GTZAN | Genre classification baseline, but has known limitations and should not be the only benchmark. |
| FMA | Genre and metadata research. |
| AudioSet | General audio pretraining; not music-specific only. |
| Million Song Dataset derivatives | Metadata and recommendation research. |

### 10.2 Training split rules

Do not randomly split clips from the same track across train and validation. Split by track, album, or artist to avoid leakage.

Recommended:

```text
train/validation/test split by artist when possible.
If not possible, split by album/release.
Never let segments from one track appear in multiple splits.
```

### 10.3 Baseline training recipe

```yaml
training:
  encoder: pretrained PaSST or AST
  encoder_freeze: true for baseline
  clip_length_sec: 10
  clips_per_track_train: random crop
  clips_per_track_eval: 8 evenly spaced
  optimizer: AdamW
  learning_rate: 1e-4 for decoder
  batch_size: 32-128 depending on GPU
  loss: BCEWithLogitsLoss
  class_imbalance: pos_weight or focal loss
  epochs: 20-100
  early_stopping: validation PR-AUC
```

### 10.4 Evaluation

Use both overall and per-category metrics.

```text
Global:
  - micro ROC-AUC
  - macro ROC-AUC
  - micro PR-AUC
  - macro PR-AUC
  - precision@k
  - recall@k

Per group:
  - genre PR-AUC
  - mood PR-AUC
  - instrument PR-AUC

Operational:
  - auto-tag precision at configured threshold
  - manual review rate
  - false-positive rate for top tags
  - inference latency per track
```

---

## 11. Implementation Details for Writing Tags

### 11.1 Format mapping example

```yaml
canonical_to_id3:
  title: "TIT2"
  artist: "TPE1"
  album_artist: "TPE2"
  album: "TALB"
  date: "TDRC"
  genre: "TCON"
  track_number: "TRCK"
  disc_number: "TPOS"
  bpm: "TBPM"
  composer: "TCOM"
  isrc: "TSRC"
  musicbrainz_recording_id: "UFID:http://musicbrainz.org"

canonical_to_vorbis:
  title: "TITLE"
  artist: "ARTIST"
  album_artist: "ALBUMARTIST"
  album: "ALBUM"
  date: "DATE"
  genre: "GENRE"
  track_number: "TRACKNUMBER"
  disc_number: "DISCNUMBER"
  bpm: "BPM"
  composer: "COMPOSER"
  isrc: "ISRC"
  musicbrainz_recording_id: "MUSICBRAINZ_TRACKID"

canonical_to_mp4:
  title: "\u00a9nam"
  artist: "\u00a9ART"
  album_artist: "aART"
  album: "\u00a9alb"
  date: "\u00a9day"
  genre: "\u00a9gen"
  track_number: "trkn"
  disc_number: "disk"
  bpm: "tmpo"
  composer: "\u00a9wrt"
```

### 11.2 Safe write procedure

```text
1. Read file.
2. Validate file is writable.
3. Create backup or metadata snapshot.
4. Compute proposed changes.
5. Dry-run diff.
6. Apply changes.
7. Re-read file.
8. Verify written values.
9. Log result.
```

### 11.3 Do not write every predicted tag to standard genre

Many players treat `genre` as a small categorical field. Do not dump mood, instrument, and free-form ML tags into `genre`.

Better:

```text
GENRE = "Synthpop; New Wave"
MOOD = "Energetic; Nostalgic"
INSTRUMENTS = "Synthesizer; Drum Machine; Electric Bass"
COMMENT or custom field = optional model provenance
```

For compatibility, optionally allow a flattened `GROUPING` or `COMMENT` field, but keep the canonical sidecar metadata as the source of truth.

---

## 12. Sidecar Metadata

For advanced tags, maintain a sidecar JSON next to the file or in a database.

Example:

```json
{
  "version": "1.0",
  "file_hash": "sha256:...",
  "model_versions": {
    "genre": "genre-chain-v1.0",
    "mood": "mood-passt-v1.0",
    "embedding": "mert-base-v1"
  },
  "predictions": {
    "genre": [
      {"tag": "Electronic", "probability": 0.91},
      {"tag": "Synthpop", "probability": 0.84}
    ],
    "mood": [
      {"tag": "Energetic", "probability": 0.79},
      {"tag": "Nostalgic", "probability": 0.62}
    ]
  },
  "embedding": {
    "type": "audio_embedding",
    "dimension": 768,
    "storage": "vector_db://track_embeddings/123"
  }
}
```

Use sidecars or a database for:

- model probabilities
- multiple candidate matches
- embeddings
- audit logs
- custom tags not supported by players
- review status

---

## 13. Human Review Workflow

A production-grade system should make review easy.

### 13.1 Review categories

```text
High-confidence auto-applied
Medium-confidence suggested
Low-confidence ignored
Conflict detected
Metadata inconsistency detected
Possible duplicate
Possible wrong release
```

### 13.2 Review UI fields

For each track:

```text
Current tags
Proposed tags
Source and confidence
Diff
Audio preview
Album context
Accept / reject / edit
Apply to album
Apply to all matching artist names
```

### 13.3 Active learning

Store corrections and use them to improve the model.

```text
User rejects "rock" and accepts "post-punk"
    ↓
Save correction
    ↓
Update alias/conflict rules
    ↓
Add to fine-tuning dataset
    ↓
Periodically retrain/calibrate
```

---

## 14. Practical Inference Pipeline Pseudocode

```python
def process_track(path, config):
    file_info = inspect_audio_file(path)

    original_tags = read_metadata(path)
    canonical = normalize_to_canonical(original_tags, file_info)

    candidates = []

    if canonical.has_musicbrainz_ids():
        candidates += lookup_by_musicbrainz_ids(canonical)

    if not high_confidence(candidates):
        fp = generate_acoustid_fingerprint(path)
        candidates += lookup_by_acoustid(fp)

    if not high_confidence(candidates):
        candidates += infer_from_filename(path)

    metadata_proposal = resolve_metadata_candidates(canonical, candidates)

    audio = decode_audio(path, sr=config.model.sample_rate, mono=True)
    clips = select_clips(len(audio) / config.model.sample_rate)

    clip_predictions = []
    for start, duration in clips:
        clip = slice_audio(audio, start, duration)
        features = preprocess_for_model(clip, config.model)
        clip_predictions.append(run_tagging_model(features))

    content_proposal = aggregate_predictions(clip_predictions)
    content_proposal = normalize_content_tags(content_proposal, config.vocabulary)
    content_proposal = apply_thresholds(content_proposal, config.thresholds)

    final_proposal = merge_proposals(
        existing=canonical,
        metadata=metadata_proposal,
        content=content_proposal,
        policy=config.write_policy
    )

    report = create_diff_report(canonical, final_proposal)

    if report.requires_review:
        enqueue_review(path, report)
    elif config.write:
        write_tags_safely(path, final_proposal, snapshot=original_tags)

    return report
```

---

## 15. Recommended Agent Instructions

Use this section directly as a prompt for an implementation LLM.

```text
You are implementing a modern music tagging system.

Build a staged pipeline with:
1. recursive file discovery,
2. metadata reading through a format-aware library,
3. canonical metadata normalization,
4. AcoustID/MusicBrainz lookup for factual metadata,
5. audio preprocessing,
6. ML inference for genre/mood/instrument tags,
7. controlled vocabulary normalization,
8. confidence-based conflict resolution,
9. dry-run review reports,
10. safe write-back with audit snapshots.

Do not treat all tags as free text.
Do not dump ML predictions into the genre field.
Do not overwrite existing tags without confidence logic.
Do not write ID3 tags into FLAC.
Do not clear existing tags unless the user explicitly enables destructive cleanup.

Use multi-label classification for descriptive tags.
Use sigmoid outputs, not softmax, for genre/mood/instrument predictions.
Use per-tag thresholds and preserve prediction probabilities in sidecar JSON.
Use album-oriented matching for release metadata.
Use sidecar JSON or a database for embeddings, confidence, model provenance, and review state.
```

---

## 16. Minimum Viable Implementation Plan

### Phase 1: Metadata-only tagger

- Read tags from files.
- Normalize into canonical schema.
- Parse filenames.
- Add MusicBrainz/AcoustID lookup.
- Create dry-run diff reports.
- Add safe write-back.

### Phase 2: Rule-based cleanup

- Controlled vocabulary.
- Alias normalization.
- Album consistency checks.
- Artwork handling.
- Duplicate detection.
- Review queue.

### Phase 3: ML content tagging

- Add audio decode and clip selection.
- Add pretrained audio encoder inference.
- Add genre/mood/instrument heads.
- Add thresholds and calibration.
- Save probabilities in sidecar JSON.

### Phase 4: Advanced model architecture

- Add classifier group chain decoder.
- Add transformer encoder support.
- Add audio-text zero-shot tagging.
- Add embedding search and similarity clustering.
- Add active learning from user corrections.

---

## 17. Suggested Technology Stack

### Python packages

```text
mutagen          metadata reading/writing
librosa          feature extraction and audio preprocessing
soundfile        audio loading
torch            model inference/training
torchaudio       audio transforms and model utilities
transformers     pretrained audio models
essentia         MIR descriptors and TensorFlow model inference
pyacoustid       AcoustID fingerprinting
musicbrainzngs   MusicBrainz API access
pydantic         canonical schema validation
rich             CLI reports
typer            CLI commands
sqlite/postgres  local metadata database
```

### Storage

Use both file tags and an internal database:

```text
Audio file tags:
  portable metadata needed by players

SQLite/Postgres:
  audit logs
  model probabilities
  embeddings
  review status
  candidate matches
  processing history
```

---

## 18. Risks and Common Failure Cases

| Risk | Mitigation |
|---|---|
| Wrong release selected | Use album-oriented matching and require review below threshold. |
| Genre vocabulary explosion | Use controlled vocabulary and aliases. |
| ML over-tags tracks | Use per-tag thresholds and max tag count. |
| Model probabilities uncalibrated | Calibrate on validation set. |
| Existing custom tags overwritten | Preserve fields and store snapshots. |
| FLAC compatibility issues | Use Vorbis Comments, not ID3. |
| WAV metadata inconsistencies | Use sidecar JSON for advanced tags. |
| Duplicate albums from remasters | Store release IDs and original dates. |
| Subjective tag disagreement | Allow user corrections and local vocabulary customization. |

---

## 19. Implementation Acceptance Criteria

A correct implementation should satisfy:

- Can scan a directory and list supported audio files.
- Can read existing metadata into a canonical schema.
- Can generate a dry-run diff without modifying files.
- Can identify at least some tracks through fingerprint or external metadata lookup.
- Can preserve existing user fields.
- Can write format-appropriate tags.
- Can avoid destructive clears by default.
- Can infer content tags with confidence scores.
- Can store advanced ML outputs in sidecar JSON or database.
- Can produce a review report for ambiguous cases.
- Can log every write operation and allow rollback from snapshots.

---

## 20. Sources Consulted

Uploaded and user-provided sources:

1. Takuya Hasumi, Tatsuya Komatsu, and Yusuke Fujita, **“Music Tagging with Classifier Group Chains,”** arXiv:2501.05050v2, 2025.
2. Yuxin Zhang and Teng Li, **“Music genre classification with parallel convolutional neural networks and capuchin search algorithm,”** *Scientific Reports*, 2025.
3. Bridge.audio, **“Music Tagging best practices - 5 tips to tag like a pro.”**
4. Engaged, **“A Guide to Tagging Music Files.”**
5. Mp3tag, **“Features – Mp3tag: the universal Tag Editor for Mac.”**

Additional implementation references:

1. Mutagen documentation: https://mutagen.readthedocs.io/
2. MusicBrainz Picard documentation: https://picard-docs.musicbrainz.org/
3. MusicBrainz Picard product page: https://picard.musicbrainz.org/
4. Essentia documentation: https://essentia.upf.edu/
5. Hugging Face audio classification documentation: https://huggingface.co/docs/transformers/en/tasks/audio_classification
6. Hugging Face Audio Course: https://huggingface.co/learn/audio-course/
7. HTS-AT paper: https://arxiv.org/abs/2202.00874
