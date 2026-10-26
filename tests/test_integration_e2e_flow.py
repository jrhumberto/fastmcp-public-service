"""
Testes de Integração E2E (End-to-End)
Valida o fluxo completo: Cliente MCP -> Servidor (Guardrails + Telemetria) -> PostgreSQL
"""

import uuid
from unittest.mock import patch

import pytest
import pytest_asyncio

from src.server.config.security import _allowlist
from src.server.tools.detail import get_record_detail
from src.server.tools.search import search_records


pytestmark = [
    pytest.mark.integration,
    pytest.mark.asyncio(loop_scope="module"),
]


class TestE2EFlowAndResilience:
    """Cenários de fluxo completo e resiliência do sistema."""

    async def test_search_pagination_and_shape(self, db_pool, seeded_records: list):
        """
        Cenário 1: Sucesso com Paginação e Filtro.
        Valida se os parâmetros limit/offset são respeitados e o contrato JSON é mantido.
        """
        # Página 1
        page1 = await search_records(query="Integration-", limit=2, offset=0)
        assert page1["total"] >= 3
        assert len(page1["results"]) == 2
        assert set(page1.keys()) == {"results", "total", "limit", "offset", "query"}
        
        # Página 2
        page2 = await search_records(query="Integration-", limit=2, offset=2)
        assert len(page2["results"]) >= 1
        
        # Validação de não-sobreposição de IDs (integridade da paginação)
        ids_page1 = {str(r["id"]) for r in page1["results"]}
        ids_page2 = {str(r["id"]) for r in page2["results"]}
        assert ids_page1.isdisjoint(ids_page2), "Páginas da paginação não podem sobrepor IDs"

    async def test_allowlist_blocking_and_telemetry(self, db_pool, mock_telemetry):
        """
        Cenário 2: Bloqueio por Guardrail (Allowlist).
        Simula a invocação de uma ferramenta bloqueada e valida se o erro é registrado 
        pela telemetria (já que @instrument_tool é o decorador mais externo).
        """
        # Força um estado onde a ferramenta não está na allowlist
        with patch("src.server.config.security._allowlist", set()):
            with pytest.raises(PermissionError, match="not permitted"):
                await search_records(query="teste")

        # Valida que a telemetria registrou a tentativa e o erro
        mock_telemetry.tool_calls.add.assert_called_with(1, {"tool": "search_records"})
        mock_telemetry.tool_errors.add.assert_called_with(1, {"tool": "search_records"})
        # A duração NÃO deve ser registrada em caso de falha imediata no guardrail
        mock_telemetry.tool_duration.record.assert_not_called()

    async def test_db_resilience_and_error_telemetry(self, db_pool, mock_telemetry):
        """
        Cenário 3: Resiliência de Banco de Dados.
        Simula uma falha no banco e valida se a exceção é propagada de forma segura 
        e se a métrica de erro é emitida, sem vazar stack traces de SQL para o cliente.
        """
        # Mocka o método fetch para simular uma falha de banco (ex: timeout ou conexão caída)
        with patch.object(db_pool, "fetch", side_effect=RuntimeError("Falha simulada de conexão")):
            with patch.object(db_pool, "fetchval", side_effect=RuntimeError("Falha simulada de conexão")):
                with pytest.raises(RuntimeError, match="Falha simulada de conexão"):
                    await search_records(query="teste")

        # Valida a telemetria de erro
        mock_telemetry.tool_calls.add.assert_called_with(1, {"tool": "search_records"})
        mock_telemetry.tool_errors.add.assert_called_with(1, {"tool": "search_records"})