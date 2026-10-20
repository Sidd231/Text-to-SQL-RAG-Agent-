import os
import sys

from dotenv import load_dotenv

try:
    import database_connection as db
    import llm_calling as mc
    try:
        import spell_check as txt
    except ImportError:
        import spellcheck as txt
except ImportError:
    from src.database import database_connection as db
    from src.model import llm_calling as mc
    from src.utils import spell_check as txt


def main():
    # Load environment variables from .env file
    load_dotenv()

    hf_token = os.getenv("HF_TOKEN") or os.getenv("hf_token")
    openai_key = os.getenv("OPENAI_API_KEY") or os.getenv("openAi") or os.getenv("openai")

    # Tables to expose to the SQL agent (including cities)
    target_tables = ["bookings", "flights", "hotels", "customers", "cities"]

    # Connect to MySQL database using env vars or provided defaults
    db_manager = db.DatabaseManager(
        host=os.getenv("DB_HOST", "localhost"),
        port=os.getenv("DB_PORT", "3306"),
        database=os.getenv("DB_NAME", "RAG"),
        username=os.getenv("DB_USER", "loco"),
        raw_password=os.getenv("DB_PASSWORD", "erRor100@23"),
    )

    # Verify database connection
    is_connected, conn_msg = db_manager.test_connection()
    if not is_connected:
        print(f"\n[Error] Could not connect to database:\n{conn_msg}")
        print("\nPlease ensure MySQL is running on localhost:3306 and check credentials in .env")
        return

    # Initialize SQL Agent Factory
    factory = mc.AgentFactory(api_key=hf_token or openai_key)
    sql_tool = factory.create_sql_tool(db_manager, target_tables)
    agent = factory.build_agent(sql_tool)

    print("=" * 60)
    print("           Travel Database SQL Assistant")
    print("=" * 60)

    # Allow passing custom question via command line arguments
    if len(sys.argv) > 1:
        question = " ".join(sys.argv[1:])
    else:
        question = "how many cities are there in your database"

    print(f"\nUser Query:      {question}")
    corrected_question = txt.check(question)
    if corrected_question != question:
        print(f"Normalized Query: {corrected_question}")

    print("\n--- Agent Execution ---")
    response = agent.run(corrected_question, max_steps=6)
    print("\n--- Final Answer ---")
    print(response)
    print("=" * 60)


if __name__ == "__main__":
    main()

    # Additional sample queries to try:
    # python main.py "How many bookings were cancelled, and what percentage of all bookings does that represent?"
    # python main.py "Which customer has spent the most money on bookings, and how much?"
    # python main.py "Show me all flights from Mumbai to Delhi that are under 2 hours in Business class."
    # python main.py "What's the total amount I'd pay for a 3-night stay at the cheapest hotel in Goa?"
    # python main.py "Which hotels in Jaipur have a pool and free wifi?"