"""Phase 4 \u2014 ``app.services`` package marker.

Required so ``app.routes.imports`` can do ``from app.services.import_parser
import parse_uploaded_statement, parse_csv_transactions`` without import
errors even when the (Phase 4 STUB) parser is eventually replaced by the
real wealthiq ``backend/app/services/import_parser.py`` lift in Phase 5+.
"""
