# Dot — a companion that reads PDFs and learns their formats

Drop a PDF. Dot reads it, shows the extracted data as an Excel-style sheet, and asks whether that's
the format you wanted. Say no and tell it what to change in plain language. Say yes and it saves the
sheet — and, the first time it meets a layout, offers to remember it as a **Profile** so the next
document of the same kind is recognised and extracted the same way.

No parser is written per vendor. The eleventh supplier costs one upload and one click, not a new
module.

Dot is also a toy: drag it, throw it, tickle it, pet it. It wanders off when bored, fidgets, catches
the PDF you drop, and walks back to its spot whenever there's work to do.

## Three screens

| Screen | What it is |
|---|---|
| **Upload** | The conversation: dropzone → sheet → *"Is this the format you wanted?"* → chat corrections → save |
| **Profiles** | Every format learned: columns, per-column hints, rules, fingerprint, sample documents |
| **Library** | Everything processed: stats, per-format usage, uploads per day, each document's sheet, conversation and PDF |

## Run

```bash
pip install -r requirements.txt
cp .env.example .env      # works as-is: LLM_PROVIDER=offline needs no key
python app.py             # http://127.0.0.1:5000
```

To use a real model, set two things in `.env`:

```
LLM_API_KEY=your-google-key
LLM_MODEL=gemini-3.1-flash-lite
```

**Leave `LLM_API_KEY` blank** and the whole app runs offline — fields come from `Key: Value` lines
and ruled tables, and the chat understands `rename X to Y`, `drop X`, `uppercase X`. Every screen
and the full learning loop work this way, which is also how the tests run.

## Using a different provider

`bot/llm.py` is the only file that names a vendor, and it holds two adapters: `GeminiAdapter` and
`OfflineAdapter`. To swap in another provider, write a class with a
`complete(pdf_path, prompt, kind)` method that returns a parsed dict and use it in `get_llm()`.

Whichever model you use must be able to **read PDFs** — text-only models will not work here.

## How it learns

- **Fingerprint** — words from page 1's letterhead, footer and first table header, with digits and
  common words stripped. Each confirmed document adds to the profile's word counts; words present in
  at least half its documents form the *core*. Matching is IDF-weighted Jaccard against each core, so
  boilerplate shared by several profiles stops being a distinguishing signal. Plain word counting —
  no model call, instant, and you can read exactly why something matched.
- **Columns** — the confirmed column list, with per-column hints and every spelling a column has been
  printed under (aliases), goes into every future extraction of that format.
- **Rules** — corrections made in chat ("use the delivery date, not the order date") are captured and
  applied on every future read. Editable and deletable on the Profiles screen.

Nothing is learned until you confirm a document. Re-confirming the same document updates it rather
than counting it twice.

## Design principle

> **Let the model read. Don't let it remember, decide, or act.**

The model returns a reply and a list of *requested* operations. It has no database access, no file
access, and no tools registered — it cannot call anything. `bot/ops.py` holds exactly 13 permitted
operations; anything else is rejected by name. Every value is cross-checked against the PDF's own
text layer, and any change that would remove most of the table stops and asks first.

That is also why format matching, verification, undo and the conversation state machine are ordinary
deterministic code: inspectable, testable without an API key, and cheap.

## Layout

```
app.py                 Flask routes, per-document locks, waitress
bot/
  llm.py               the only file that names a vendor
  flow.py              conversation state machine -> envelope {doc, table, bot, transcript, changes}
  dialogue.py          every line Dot says
  extract.py           extraction prompt, validation, flatten, verify against the text layer
  ops.py               the 13 table operations (chat and manual edits share them)
  profiles.py          fingerprint, matching, learning
  pdftext.py           PDF inspection (text layer, page-1 tokens, size caps)
  excel.py             xlsx (green header) + csv
  history.py, db.py    SQLite document store, undo stack
static/
  app.js               SPA: Upload / Profiles / Library, Excel-style grid, chat
  robot.js             Dot's drawing: SVG rig + procedural animation
  world.js             Dot's body: floating layer, drag/throw physics, wander, fidgets, catch
  companion.js         mood state machine; swaps to Lottie art if static/art/ has files
  app.css              base design system
  companion.css        everything above
data/                  app.db, uploads/, outputs/   (gitignored)
```

## API

```
POST /api/upload                           multipart "file" -> envelope
POST /api/docs/<id>/extract                run the model -> envelope
POST /api/docs/<id>/answer  {option,...}   button clicks (yes/no/profile:<id>/submit ...)
POST /api/docs/<id>/chat    {message}      free text
POST /api/docs/<id>/ops     {ops:[...]}    manual edits (set_cell, rename_col, drop_col, ...)
POST /api/docs/<id>/undo  ·  /revise
GET  /api/docs?q=&unfinished=1  ·  GET/DELETE /api/docs/<id>  ·  /download.xlsx|csv  ·  /pdf
GET/POST /api/profiles  ·  GET/PUT/DELETE /api/profiles/<id>
GET  /api/stats  ·  /api/health
```

## Limits worth knowing

- Verification confirms a value **appears in the document**, not that it belongs in that cell. A real
  value placed on the wrong row passes.
- Scanned PDFs with no text layer extract fine but cannot be verified — the sheet says so.
- Caps: 20 MB, 80 pages.
- Each chat message re-sends the PDF and the table, so cost scales with page count, not row count.

## Custom art

Dot is drawn in code (`robot.js`) so it needs no assets. To replace it with commissioned animation,
drop Lottie JSON files into `static/art/` named after the states (`idle.json`, `reading.json`, ...)
and it switches automatically. See `static/art/README.md`.
