
# Advisory Data API

## Import JSON advisory data

```powershell
env\Scripts\python.exe manage.py import_json D:\agrodata
```

Use `--dry-run` to validate files without writing to the database, or `--clear`
to delete existing advisory rows before importing.

## RAG query API

Start Django:

```powershell
env\Scripts\python.exe manage.py runserver
```

Send a question:

```http
POST /api/rag/query/
Content-Type: application/json

{
  "question": "How do I manage banana pests?",
  "value_chain": "banana",
  "limit": 5,
  "include_sources": true
}
```

`value_chain` is optional. The API retrieves matching rows from SQLite and uses
them as context for the answer. `include_sources` is optional and defaults to
`false`.

To enable LLM responses, set an API key before starting the server:

```powershell
$env:OPENAI_API_KEY="your_api_key"
$env:LLM_MODEL="gpt-4o-mini"
```

Without an API key, the endpoint still returns a friendly response using the
best retrieved advisory row.
