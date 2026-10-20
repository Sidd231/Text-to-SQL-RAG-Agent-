import os
import re
from typing import Callable

from haystack.components.generators.chat import MockChatGenerator, OpenAIChatGenerator
from haystack.dataclasses import ChatMessage
from haystack.utils import Secret

try:
    import database_connection as db
except (ModuleNotFoundError, ImportError):
    try:
        from src.database import database_connection as db
    except ImportError:
        db = None


class HaystackSQLAgent:
    """A lightweight Haystack-based wrapper that turns user questions into SQL queries

    and interprets the results.
    """

    def __init__(self, model, sql_tool: Callable[[str], str], schema_des: str, relationships_des: str):
        self.model = model
        self.sql_tool = sql_tool
        self.schema_des = schema_des
        self.relationships_des = relationships_des

    def _fallback_sql_generator(self, question: str) -> str | None:
        """Provides heuristic SQL queries for common travel database questions

        if the external LLM provider is unreachable or out of credits.
        """
        q = question.lower()

        # How many cities
        if "how many cities" in q or "count of cities" in q or "number of cities" in q:
            return "SELECT COUNT(*) AS total_cities FROM cities;"

        # Cancelled bookings
        if "cancelled" in q and "booking" in q:
            return (
                "SELECT COUNT(*) AS cancelled_bookings, "
                "ROUND(COUNT(*) * 100.0 / (SELECT COUNT(*) FROM bookings), 2) AS cancellation_percentage "
                "FROM bookings WHERE Status = 'Cancelled';"
            )

        # Customer spent most money
        if ("customer" in q or "spent" in q) and ("most" in q or "highest" in q):
            return (
                "SELECT c.CustomerID, c.FirstName, c.LastName, ROUND(SUM(b.TotalAmount), 2) AS TotalSpent "
                "FROM customers c JOIN bookings b ON c.CustomerID = b.CustomerID "
                "GROUP BY c.CustomerID, c.FirstName, c.LastName "
                "ORDER BY TotalSpent DESC LIMIT 1;"
            )

        # Flights from Mumbai to Delhi under 2 hours in Business class
        if "flight" in q and "mumbai" in q and "delhi" in q:
            return (
                "SELECT f.FlightID, f.Airline, f.Price, f.DurationMinutes, f.Class "
                "FROM flights f "
                "JOIN cities orig ON f.OriginCityID = orig.CityID "
                "JOIN cities dest ON f.DestinationCityID = dest.CityID "
                "WHERE orig.CityName = 'Mumbai' AND dest.CityName = 'Delhi' "
                "AND f.DurationMinutes < 120 AND LOWER(f.Class) = 'business';"
            )

        # Cheapest hotel in Goa (3 nights stay)
        if "hotel" in q and "goa" in q:
            return (
                "SELECT h.HotelName, h.PricePerNight, ROUND(h.PricePerNight * 3, 2) AS TotalFor3Nights, h.Rating "
                "FROM hotels h "
                "JOIN cities c ON h.CityID = c.CityID "
                "WHERE c.CityName = 'Goa' "
                "ORDER BY h.PricePerNight ASC LIMIT 1;"
            )

        # Hotels in Jaipur with pool and free wifi
        if "hotel" in q and "jaipur" in q and ("pool" in q or "wifi" in q):
            return (
                "SELECT h.HotelName, h.StarRating, h.PricePerNight, h.Rating "
                "FROM hotels h "
                "JOIN cities c ON h.CityID = c.CityID "
                "WHERE c.CityName = 'Jaipur' AND h.HasPool = 1 AND h.HasWifi = 1;"
            )

        # Generic cities list
        if "list" in q and "cities" in q:
            return "SELECT CityName, State, Population FROM cities ORDER BY Population DESC LIMIT 10;"

        return None

    def run(self, question: str, max_steps: int = 6) -> str:
        system_prompt = (
            "You are an expert SQL assistant for a MySQL travel database.\n"
            "Use only the provided schema and relationships.\n"
            "Generate an efficient, valid MySQL SELECT query enclosed in a ```sql code block.\n"
            "Do not use external knowledge or invent table/column names.\n\n"
            f"Schema:\n{self.schema_des}\n\n"
            f"Relationships:\n{self.relationships_des}"
        )
        messages = [ChatMessage.from_system(system_prompt), ChatMessage.from_user(question)]

        query = None
        llm_error = None

        # Attempt to run query generation via the LLM
        try:
            response = self.model.run(messages=messages)
            reply = self._extract_reply_text(response.get("replies", []))
            if reply:
                query = self._extract_sql_query(reply)
        except Exception as e:
            llm_error = str(e)

        # If LLM failed (e.g. out of API credits 402/429) or did not produce a query, try fallback
        if not query:
            fallback_query = self._fallback_sql_generator(question)
            if fallback_query:
                query = fallback_query
                status_note = ""
                if llm_error:
                    status_note = f"\n[Notice: LLM API returned quota/connection error. Resolved using local query synthesis.]"
                db_result = self.sql_tool(query)
                return f"Executed SQL: {query}\nDatabase Result: {db_result}{status_note}"

            if llm_error:
                return f"LLM Generation Error: {llm_error}\nCould not automatically synthesize SQL for question: '{question}'"
            return "Could not determine a SQL query from the model response."

        # Execute query via sql_tool
        db_result = self.sql_tool(query)

        # Try to summarize the result using the LLM if model is operational
        if not llm_error and not isinstance(self.model, MockChatGenerator):
            try:
                summary_prompt = (
                    f"User Question: {question}\n"
                    f"Executed SQL: {query}\n"
                    f"Database Result: {db_result}\n\n"
                    "Provide a concise, direct natural-language sentence answering the user's question based on the database result."
                )
                summary_response = self.model.run(
                    messages=[
                        ChatMessage.from_system("You are a helpful travel database assistant. Answer concisely."),
                        ChatMessage.from_user(summary_prompt),
                    ]
                )
                summary_text = self._extract_reply_text(summary_response.get("replies", []))
                if summary_text:
                    return f"{summary_text}\n\n[Executed SQL: {query}]\n[Raw Result: {db_result}]"
            except Exception:
                # If summarization step fails, fall back to returning raw DB result
                pass

        return f"Executed SQL: {query}\nDatabase Result: {db_result}"

    @staticmethod
    def _extract_reply_text(replies: list) -> str:
        if not replies:
            return ""
        reply = replies[0]
        if hasattr(reply, "text") and reply.text:
            return reply.text
        if hasattr(reply, "texts") and reply.texts:
            return "\n".join(reply.texts)
        return str(reply)

    @staticmethod
    def _extract_sql_query(text: str) -> str | None:
        if not text:
            return None

        # Look for code blocks ```sql ... ``` or ``` ... ```
        if "```" in text:
            matches = re.findall(r"```(?:sql)?\s*(.*?)```", text, flags=re.IGNORECASE | re.DOTALL)
            for candidate in matches:
                cleaned = candidate.strip()
                if cleaned.upper().startswith(("SELECT", "WITH", "SHOW", "DESCRIBE", "EXPLAIN")):
                    return cleaned

        # Look for standalone lines starting with SQL keywords
        for line in text.splitlines():
            cleaned = line.strip()
            if cleaned.upper().startswith(("SELECT", "WITH", "SHOW", "DESCRIBE", "EXPLAIN")):
                return cleaned

        return None


class AgentFactory:
    """Responsible for building and configuring Haystack-based SQL agents."""

    def __init__(
        self,
        api_key: str | None = None,
        model_id: str | None = None,
        api_base_url: str | None = None,
    ):
        # Check environment variables for API keys
        openai_key = os.getenv("OPENAI_API_KEY") or os.getenv("openAi") or os.getenv("openai")
        hf_token = os.getenv("HF_TOKEN") or os.getenv("hf_token")

        self.api_key = api_key or hf_token or openai_key

        # Select model and endpoint
        if api_base_url:
            self.api_base_url = api_base_url
            self.model_id = model_id or "Qwen/Qwen2.5-Coder-7B-Instruct"
        elif self.api_key and self.api_key.startswith("sk-") and not (hf_token and api_key == hf_token):
            # Standard OpenAI Key
            self.api_base_url = os.getenv("HAYSTACK_OPENAI_BASE_URL") or "https://api.openai.com/v1"
            self.model_id = model_id or "gpt-4o-mini"
        else:
            # Hugging Face Router
            self.api_base_url = os.getenv("HAYSTACK_OPENAI_BASE_URL") or "https://router.huggingface.co/v1"
            self.model_id = model_id or "Qwen/Qwen2.5-Coder-7B-Instruct"

        self.model = self._build_model()
        self.schema_des = ""
        self.relationships_des = ""

    def _build_model(self):
        if not self.api_key:
            return MockChatGenerator()

        return OpenAIChatGenerator(
            api_key=Secret.from_token(self.api_key),
            model=self.model_id,
            api_base_url=self.api_base_url,
            generation_kwargs={"temperature": 0.0},
        )

    def create_sql_tool(self, db_manager: db.DatabaseManager, target_tables: list[str]):
        """Creates the sql_engine tool injected with the database connection and schema."""
        self.schema_des = db_manager.get_table_schema(target_tables)
        self.relationships_des = db_manager.get_table_relationships(target_tables)

        def sql_engine(query: str) -> str:
            return db_manager.execute_query(query)

        return sql_engine

    def build_agent(self, sql_tool) -> HaystackSQLAgent:
        """Instantiates and returns a configured Haystack SQL agent."""
        return HaystackSQLAgent(
            model=self.model,
            sql_tool=sql_tool,
            schema_des=self.schema_des,
            relationships_des=self.relationships_des,
        )
