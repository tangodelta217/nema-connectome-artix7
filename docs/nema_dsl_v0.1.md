# NEMA-DSL v0.1 (Scaffold Draft)

## Goal
NEMA-DSL v0.1 compiles to NEMA-IR JSON with 1:1 structural intent.
This stage defines grammar and lowering rules; parser/typechecker implementation is intentionally pending.

## EBNF

```ebnf
File          = { Stmt } EOF ;

Stmt          = Assignment ";"
              | Block
              | TypedObjectStmt
              ;

Assignment    = IDENT "=" Value ;

Block         = IDENT "{" { Stmt } "}" ;

TypedObjectStmt = IDENT Object ;

Value         = Scalar
              | List
              | Object
              | TypedObject
              ;

TypedObject   = IDENT Object ;

Object        = "{" { Pair [","] } "}" ;
Pair          = (IDENT | String) ":" Value ;

List          = "[" [ Value { "," Value } ] "]" ;

Scalar        = String
              | INT
              | IDENT
              | TimeLiteral
              | FixedLiteral
              ;

TimeLiteral   = INT TimeUnit ;
TimeUnit      = "ns" | "us" | "ms" | "s" ;

FixedLiteral  = TypeId "(" INT ["u"] ")" ;
TypeId        = IDENT ;

String        = '"' { Escape | Char } '"' ;
Escape        = "\\" ("\\" | '"' | "n" | "r" | "t") ;
```

## Lexer Rules

- Whitespace is ignored except as token separator.
- Comments:
  - `# ...` to end-of-line
  - `// ...` to end-of-line
- Strings:
  - double-quoted
  - escapes supported: `\\`, `\"`, `\n`, `\r`, `\t`
- `IDENT`:
  - regex intent: `[A-Za-z_][A-Za-z0-9_\.\-/]*`
- `INT`:
  - decimal integer literal, regex intent: `[0-9]+`

## Special Literals

### TimeLiteral
Syntax: `INT + {ns|us|ms|s}`

Lowering shape:

```json
{"nanoseconds": "<int>"}
```

Conversion:
- `ns` -> `x`
- `us` -> `x * 1_000`
- `ms` -> `x * 1_000_000`
- `s`  -> `x * 1_000_000_000`

Result is serialized as decimal string in `nanoseconds`.

### FixedLiteral
Syntax: `TypeId(INT[ u ])`

Lowering shape:

Signed raw:

```json
{"typeId":"Q8.8","signedRaw":"-12"}
```

Unsigned raw:

```json
{"typeId":"UQ8.8","unsignedRaw":"12"}
```

Rules:
- trailing `u` selects `unsignedRaw`
- no trailing `u` selects `signedRaw`
- raw integer is serialized as decimal string

## Lowering Rules

- `IDENT` used as a scalar lowers to JSON string.
  - Example: `policy = nema.tick.v0.1;` -> `"policy": "nema.tick.v0.1"`
- Typed object form `tag { ... }` lowers exactly as `{ ... }`.
  - `tag` is ignored at v0.1 scaffold stage.
- Lists and objects lower recursively using the same rules.

## Compilation Target

- Primary target: NEMA-IR JSON (deterministic shape and ordering as defined by pipeline conventions).
- Secondary target: protobuf flow remains via existing repository pipeline where applicable.
- Semantic objective: compile 1:1 to existing NEMA-IR contract without changing numeric semantics.
