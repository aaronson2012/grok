import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from src.services.persona_service import PersonaService


@pytest.fixture
def persona_service():
    return PersonaService()


@pytest.fixture
def mock_db():
    with patch("src.services.persona_service.db") as mock:
        mock.conn = MagicMock()
        yield mock


class TestGetAllPersonas:
    @pytest.mark.asyncio
    async def test_returns_standard_first(self, persona_service, mock_db):
        standard_cursor = MagicMock()
        standard_cursor.fetchall = AsyncMock(return_value=[
            {"id": 1, "name": "Standard", "description": "Default persona"}
        ])
        standard_cursor.__aenter__ = AsyncMock(return_value=standard_cursor)
        standard_cursor.__aexit__ = AsyncMock()
        
        others_cursor = MagicMock()
        others_cursor.fetchall = AsyncMock(return_value=[
            {"id": 2, "name": "Batman", "description": "Dark Knight"},
            {"id": 3, "name": "Pirate", "description": "Arr matey"},
        ])
        others_cursor.__aenter__ = AsyncMock(return_value=others_cursor)
        others_cursor.__aexit__ = AsyncMock()
        
        mock_db.conn.execute = MagicMock(side_effect=[standard_cursor, others_cursor])
        
        result = await persona_service.get_all_personas()
        
        assert len(result) == 3
        assert result[0]["name"] == "Standard"
        assert result[1]["name"] == "Batman"
        assert result[2]["name"] == "Pirate"


class TestGetDeletablePersonas:
    @pytest.mark.asyncio
    async def test_excludes_standard(self, persona_service, mock_db):
        cursor = MagicMock()
        cursor.fetchall = AsyncMock(return_value=[
            {"id": 2, "name": "Custom1", "description": "Custom persona 1"},
            {"id": 3, "name": "Custom2", "description": "Custom persona 2"},
        ])
        cursor.__aenter__ = AsyncMock(return_value=cursor)
        cursor.__aexit__ = AsyncMock()
        mock_db.conn.execute = MagicMock(return_value=cursor)
        
        result = await persona_service.get_deletable_personas()
        
        assert len(result) == 2
        for persona in result:
            assert persona["name"] != "Standard"


class TestGetPersonaById:
    @pytest.mark.asyncio
    async def test_returns_persona(self, persona_service, mock_db):
        cursor = MagicMock()
        cursor.fetchone = AsyncMock(return_value={
            "id": 1, "name": "Standard", "description": "Default", "system_prompt": "You are helpful"
        })
        cursor.__aenter__ = AsyncMock(return_value=cursor)
        cursor.__aexit__ = AsyncMock()
        mock_db.conn.execute = MagicMock(return_value=cursor)
        
        result = await persona_service.get_persona_by_id(1)
        
        assert result["name"] == "Standard"
        assert result["system_prompt"] == "You are helpful"

    @pytest.mark.asyncio
    async def test_returns_none_for_missing(self, persona_service, mock_db):
        cursor = MagicMock()
        cursor.fetchone = AsyncMock(return_value=None)
        cursor.__aenter__ = AsyncMock(return_value=cursor)
        cursor.__aexit__ = AsyncMock()
        mock_db.conn.execute = MagicMock(return_value=cursor)
        
        result = await persona_service.get_persona_by_id(999)
        
        assert result is None


class TestGetPersonaName:
    @pytest.mark.asyncio
    async def test_returns_name(self, persona_service, mock_db):
        cursor = MagicMock()
        cursor.fetchone = AsyncMock(return_value={"name": "Batman"})
        cursor.__aenter__ = AsyncMock(return_value=cursor)
        cursor.__aexit__ = AsyncMock()
        mock_db.conn.execute = MagicMock(return_value=cursor)
        
        result = await persona_service.get_persona_name(2)
        
        assert result == "Batman"

    @pytest.mark.asyncio
    async def test_returns_unknown_for_missing(self, persona_service, mock_db):
        cursor = MagicMock()
        cursor.fetchone = AsyncMock(return_value=None)
        cursor.__aenter__ = AsyncMock(return_value=cursor)
        cursor.__aexit__ = AsyncMock()
        mock_db.conn.execute = MagicMock(return_value=cursor)
        
        result = await persona_service.get_persona_name(999)
        
        assert result == "Unknown"


class TestSetGuildPersona:
    @pytest.mark.asyncio
    async def test_sets_persona(self, persona_service, mock_db):
        mock_db.conn.execute = AsyncMock()
        mock_db.conn.commit = AsyncMock()
        
        await persona_service.set_guild_persona(guild_id=123, persona_id=5)
        
        mock_db.conn.execute.assert_called_once()
        mock_db.conn.commit.assert_called_once()
        
        call_args = mock_db.conn.execute.call_args[0]
        assert "INSERT INTO guild_configs" in call_args[0]
        assert call_args[1] == (123, 5)


class TestGetCurrentPersona:
    @pytest.mark.asyncio
    async def test_returns_current_persona(self, persona_service, mock_db):
        cursor = MagicMock()
        cursor.fetchone = AsyncMock(return_value={
            "name": "Pirate", "description": "Talks like a pirate"
        })
        cursor.__aenter__ = AsyncMock(return_value=cursor)
        cursor.__aexit__ = AsyncMock()
        mock_db.conn.execute = MagicMock(return_value=cursor)
        
        result = await persona_service.get_current_persona(guild_id=123)
        
        assert result["name"] == "Pirate"
        assert result["description"] == "Talks like a pirate"

    @pytest.mark.asyncio
    async def test_returns_none_when_not_set(self, persona_service, mock_db):
        cursor = MagicMock()
        cursor.fetchone = AsyncMock(return_value=None)
        cursor.__aenter__ = AsyncMock(return_value=cursor)
        cursor.__aexit__ = AsyncMock()
        mock_db.conn.execute = MagicMock(return_value=cursor)
        
        result = await persona_service.get_current_persona(guild_id=999)
        
        assert result is None


class TestDeletePersona:
    @pytest.mark.asyncio
    async def test_deletes_and_returns_name(self, persona_service, mock_db):
        mock_db.conn.execute = AsyncMock()
        mock_db.conn.commit = AsyncMock()
        
        with patch.object(persona_service, "get_persona_name", new=AsyncMock(return_value="OldPersona")):
            result = await persona_service.delete_persona(persona_id=5)
            
            assert result == "OldPersona"
            mock_db.conn.execute.assert_called()
            mock_db.conn.commit.assert_called()


class TestCreatePersona:
    @pytest.mark.asyncio
    async def test_handles_ai_failure(self, persona_service, mock_db):
        with patch("src.services.persona_service.ai_service") as mock_ai:
            mock_ai.generate_response = AsyncMock(side_effect=Exception("API Error"))
            
            success, result = await persona_service.create_persona(
                user_input="Create a persona",
                created_by=12345,
            )
            
            assert success is False
            assert "failed" in result.lower()
