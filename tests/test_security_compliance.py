""
Testes de Integração de Segurança e Conformidade (LGPD/OWASP)
Valida prevenção de injeção SQL, validação de esquemas e manipulação segura de dados.
"""

import uuid

import pytest
import pytest_asyncio

from src.server.tools.detail import get_record_detail
from src.server.tools.search import search_records
from src.server.tools.stats import get_statistics


pytestmark = [
    pytest.mark.integration,
    pytest.mark.asyncio(loop_scope="module"),
]


@pytest_asyncio.fixture(loop_scope="module")
async def security_seeded_records(db_pool):
    """
    Insere registros com payloads de borda para testar regras de segurança.
    Faz a limpeza automática após os testes.
    """
    tag = str(uuid.uuid4())[:8]
    ids = []

    # Payloads de teste
    test_cases = [
        # 1. Tentativa de Injeção SQL clássica no campo de texto
        (f"SQLi-{tag}", "'; DROP TABLE records;--", "active", "typeA", "cat1"),
        # 2. Simulação de PII (Dados Pessoais) para validação futura de mascaramento
        (f"PII-{tag}", "CPF do servidor: 123.456.789-00 | Email: teste@dominio.com", "active", "typeB", "cat2"),
        # 3. Caracteres especiais e UTF-8
        (f"UTF8-{tag}", "Nome com acento: João & Emoji: 🏛️", "inactive", "typeA", "cat1"),
    ]

    for name, desc, status, type_, category in test_cases:
        row = await db_pool.fetchrow(
            """
            INSERT INTO records (name, description, status, type, category)
            VALUES ($1, $2, $3, $4, $5)
            RETURNING id
            """,
            name, desc, status, type_, category,
        )
        ids.append(row["id"])

    yield ids

    # Cleanup
    for rid in ids:
        await db_pool.execute("DELETE FROM records WHERE id = $1", rid)


class TestSecurityAndCompliance:
    """Cenários de validação de segurança e conformidade."""

    async def test_sql_injection_prevention_parameterized(self, db_pool, security_seeded_records):
        """
        Valida que a injeção SQL é tratada como string literal devido ao uso 
        de parâmetros posicionais ($1) do asyncpg, retornando 0 resultados 
        em vez de executar o comando malicioso.
        """
        malicious_query = "'; DROP TABLE records;--"
        result = await search_records(query=malicious_query)
        
        # Deve procurar pela string literal exata, não executar o DROP
        assert result["total"] == 0
        assert len(result["results"]) == 0

    async def test_filter_column_injection_prevention(self, db_pool):
        """
        Valida que a validação de `allowed_filter_cols` bloqueia tentativas 
        de injeção de colunas maliciosas ANTES de qualquer interação com o banco.
        """
        malicious_filter = {"'; DROP TABLE records;--": "x"}
        
        with pytest.raises(ValueError, match="Invalid filter column"):
            await search_records(query="teste", filters=malicious_filter)

    async def test_group_by_column_injection_prevention(self, db_pool):
        """
        Valida que a validação de `allowed_group_fields` em get_statistics 
        impede a injeção de SQL via cláusula GROUP BY.
        """
        malicious_group = "status; SELECT pg_sleep(10);--"
        
        with pytest.raises(ValueError, match="Invalid group_by field"):
            await get_statistics(group_by=malicious_group)

    async def test_pii_data_retrieval_safety(self, db_pool, security_seeded_records):
        """
        Valida que dados sensíveis inseridos no banco são recuperados com sucesso 
        e mantêm sua integridade (UTF-8). 
        NOTA: Se um middleware de mascaramento de PII for implementado no futuro, 
        as asserções abaixo devem ser atualizadas para validar o formato mascarado 
        (ex: '***.***.***-00').
        """
        # Busca o registro de PII pelo nome único
        result = await search_records(query="PII-")
        
        assert result["total"] == 1
        record = result["results"][0]
        
        # Valida integridade dos dados recuperados
        assert "123.456.789-00" in record["description"]
        assert "teste@dominio.com" in record["description"]
        
        # Valida que caracteres especiais/UTF-8 não corromperam no banco/asyncpg
        utf8_result = await search_records(query="UTF8-")
        assert "João & Emoji: 🏛️" in utf8_result["results"][0]["description"]

    async def test_detail_tool_safe_error_handling(self, db_pool):
        """
        Valida que a busca por um ID inexistente retorna um dicionário de erro 
        estruturado, em vez de lançar uma exceção não tratada ou expor detalhes 
        internos do banco de dados.
        """
        fake_uuid = str(uuid.uuid4())
        result = await get_record_detail(record_id=fake_uuid)
        
        assert isinstance(result, dict)
        assert "error" in result
        assert "record_id" in result
        assert result["record_id"] == fake_uuid
        # Garante que não há chave 'traceback' ou 'sql' exposta no erro
        assert "traceback" not in result
        assert "sql" not in result