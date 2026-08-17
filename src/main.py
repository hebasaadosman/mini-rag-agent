from fastapi import FastAPI
from models.ChunkModel import ChunkModel
from observability.langsmith import configure_langsmith
from routes import auth, base,data,nlp,workflow
from helpers.config import get_settings, Settings
from stores.llm.LLMProviderFactory import LLMProviderFactory
from stores.vectordb.VectorDBProviderFactory import VectorDBProviderFactory
from stores.llm.templates.template_parser import TemplateParser
from sqlalchemy.ext.asyncio import create_async_engine,AsyncSession
from sqlalchemy.orm import sessionmaker
from utils.mertrics import setup_metrics_route
from controllers.NLPController import NLPController
from controllers import KnowledgeAgentController, MultiAgentController
from models.AssetModel import AssetModel
from models.ProjectModel import ProjectModel
from routes import agents
from agents.knowledge_agent.tools_service import (
    KnowledgeAgentToolsService,
)
from persistence.checkpointing import (
    create_postgres_checkpointer,
)
from utils.async_keyed_lock import PostgresAdvisoryKeyedLock
from infrastructure.email import create_send_email_tool
settings = get_settings()

configure_langsmith(settings)
app = FastAPI()

@app.on_event("startup")
async def startup_db_client():

    # app.db_mongo_conn = AsyncIOMotorClient(settings.MONGODB_URI)
    postgres_conn = f"postgresql+asyncpg://{settings.POSTGRES_USER}:{settings.POSTGRES_PASSWORD}@{settings.POSTGRES_HOST}:{settings.POSTGRES_PORT}/{settings.POSTGRES_DB}"
    app.pg_engine = create_async_engine(postgres_conn, echo=True)
    app.db_client = sessionmaker(app.pg_engine, class_=AsyncSession, expire_on_commit=False)

    llm_provider_factory = LLMProviderFactory(config=settings.dict())
    vector_db_provider_factory = VectorDBProviderFactory(config=settings.dict(),db_client=app.db_client)
    app.generation_client = llm_provider_factory.create_provider(settings.GENERATION_BACKEND)
    app.embedding_client = llm_provider_factory.create_provider(settings.EMBEDDING_BACKEND)

    app.generation_client.set_generation_model(settings.GENEERATION_MODEL_ID)
    app.embedding_client.set_embedding_model(model_id=settings.EMBEDDING_MODEL_ID, model_size=settings.EMBEDDING_MODEL_SIZE)

    app.vectordb_client = vector_db_provider_factory.create_provider(settings.VECTOR_DB_BACKEND, db_path=settings.VECTOR_DB_PATH, distance_metric_method=settings.VECTOR_DB_DISTANCE_METRIC_METHOD)
    await app.vectordb_client.connect()
    app.template_parser = TemplateParser(
        language=settings.PRIMARY_LANGUAGE,
        default_language=settings.DEFAULT_LANGUAGE,
    )
    app.asset_model = await AssetModel.create_instance(
    db_client=app.db_client,
    )

    app.project_model = await ProjectModel.create_instance(
        db_client=app.db_client,
    )
    chunk_model = await ChunkModel.create_instance(
        db_client=app.db_client,
    )
    app.nlp_controller = NLPController(
        vectordb_client=app.vectordb_client,
        generation_client=app.generation_client,
        embedding_client=app.embedding_client,
        template_parser=app.template_parser,
    )

    app.knowledge_agent_tools_service = (
        KnowledgeAgentToolsService(
            asset_model=app.asset_model,
            project_model=app.project_model,
            chunk_model=chunk_model,
            nlp_controller=app.nlp_controller,
        )
    )
    app.agent_memory_max_messages = (
        settings.AGENT_MEMORY_MAX_MESSAGES
    )
    # The agent receives only this approved-delivery tool. SMTP credentials
    # remain private inside the infrastructure adapter.
    app.send_email_tool = create_send_email_tool(settings)
    app.agent_thread_locks = PostgresAdvisoryKeyedLock(
        app.pg_engine
    )
    app.checkpointer_context = (
        create_postgres_checkpointer(
            settings
        )
    )

    app.checkpointer = (
        await app.checkpointer_context.__aenter__()
    )

    app.knowledge_agent_controller = KnowledgeAgentController(
        generation_client=app.generation_client,
        tools_service=app.knowledge_agent_tools_service,
        project_model=app.project_model,
        checkpointer=app.checkpointer,
        max_memory_messages=app.agent_memory_max_messages,
    )
    app.multi_agent_runtime = (
        llm_provider_factory.create_multi_agent_runtime(
            llm_provider=app.generation_client,
            knowledge_agent_factory=(
                app.knowledge_agent_controller.build_agent
            ),
            send_email_tool=app.send_email_tool,
            checkpointer=app.checkpointer,
            max_memory_messages=app.agent_memory_max_messages,
        )
    )
    app.multi_agent_controller = MultiAgentController(
        runtime=app.multi_agent_runtime,
        project_model=app.project_model,
    )

@app.on_event("shutdown")
async def shutdown_db_client():
    if getattr(app, "checkpointer_context", None):
        await app.checkpointer_context.__aexit__(None, None, None)
    # app.db_client.close_all_sessions()
    if getattr(app, "vectordb_client", None):
        await app.vectordb_client.disconnect()
    if getattr(app, "pg_engine", None):
        await app.pg_engine.dispose()


app.include_router(base.base_router)
app.include_router(auth.auth_router)
app.include_router(data.data_router)
app.include_router(nlp.nlp_router)
app.include_router(workflow.workflow_router)
app.include_router(agents.agents_router)


setup_metrics_route(app)
