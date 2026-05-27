from fastapi import FastAPI, UploadFile, File, Depends
from fastapi.middleware.cors import CORSMiddleware

from sqlalchemy.orm import Session
from sqlalchemy import func

from sqlalchemy import desc

from pydantic import BaseModel
from openai import OpenAI
from dotenv import load_dotenv
from datetime import datetime
import fitz
import os
from fastapi import Header
from database import Base, engine, get_db
from models import (
    ChatMessage,
    User,
    Log,
    Conversation
)

from routes.auth_routes import (
    router as auth_router,
    get_current_user,
    get_optional_user
)
# LOAD ENV
load_dotenv()

app = FastAPI()

# CREATE TABLES
Base.metadata.create_all(bind=engine)

app.include_router(auth_router)
# ---------------- CORS ----------------


app.add_middleware(
    CORSMiddleware,
    allow_origins=[
    "http://localhost:5173",
    "https://auli-frontend.vercel.app"
],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------- CURRENT KEYWORDS ----------------

current_keywords = [
    "current",
    "latest",
    "today",
    "now",
    "recent",
]

# ---------------- CODING KEYWORDS ----------------

coding_keywords = [
    "code",
    "html",
    "css",
    "javascript",
    "js",
    "python",
    "react",
    "node",
    "express",
    "api",
    "build",
    "create",
    "make",
    "develop",
    "app",
    "website",
    "game",
    "program",
    "frontend",
    "backend",
]
# ---------------- OPENROUTER ----------------

client = OpenAI(
    api_key=os.getenv("OPENROUTER_API_KEY"),
    base_url="https://openrouter.ai/api/v1"
)

# ---------------- REQUEST MODEL ----------------

class ChatRequest(BaseModel):
    message: str
    history: list = []
    pdfText: str = ""
    conversation_id: int | None = None
    mode: str = "study"
# ---------------- CHAT ENDPOINT ----------------

@app.post("/chat")
async def chat(
    req: ChatRequest,
    x_guest_token: str = Header(None),
    current_user: dict | None = Depends(get_optional_user),
    db: Session = Depends(get_db)
               ):

    try:

        pdf_text = req.pdfText
        mode = req.mode.lower()

        # =========================
        # DETECT CURRENT AFFAIRS
        # =========================

        is_current_question = any(
            word in req.message.lower()
            for word in current_keywords
        )

        # =========================
        # DETECT CODING AFFAIRS
        # =========================

        is_code_request = any(
            word in req.message.lower()
            for word in coding_keywords
        )
        # =========================
        # FINAL PROMPT
        # =========================

        if pdf_text.strip():

            final_prompt = f"""
User Question:
{req.message}

Study Material:
{pdf_text}
"""

        else:

            final_prompt = req.message

        # =========================
        # SYSTEM PROMPT
        # =========================

        system_prompt = """
You are AuLi AI, an advanced educational and coding assistant.

Core Rules:
- Answer clearly, accurately, and directly.
- Keep responses concise but high quality.
- Use markdown formatting properly.
- Use headings, bullet points, and sections.
- Never repeat the user's question.
- Never generate incomplete answers.
- Avoid filler text.
- Answer clearly and accurately. 
- Always give COMPLETE working code. 
- Use modern UI styling. 
- Use markdown formatting. 
- Avoid repeating the question. 
- Keep answers concise but informative. 
- Use headings and bullet points when useful. 
- Make responses feel like smart study notes. 
- Do not mention knowledge cutoff dates unless specifically asked. 

Coding Rules:
- Always provide COMPLETE working code.
- Never leave unfinished functions.
- Ensure brackets and syntax are correct.
- Separate HTML, CSS, and JavaScript into different code blocks.
- Label files clearly.
- Prefer modern clean UI designs.
- Make apps interactive and polished.
- Use responsive layouts.
- Avoid overly long explanations after code.
- Prioritize correctness over creativity.

Formatting Rules:
- Use triple backticks for all code.
- Keep explanations short and useful.
- Do not dump giant raw text walls.
"""


# =========================
# MODE SYSTEM
# =========================

        STUDY_PROMPT = """
You are AuLi AI in STUDY MODE.

Your job is to teach like a smart, friendly tutor.

Rules:
- Explain concepts clearly and step-by-step
- Keep answers beginner-friendly
- Use examples whenever helpful
- Use headings and bullet points
- Focus on understanding, not memorization
- If user is confused, simplify further
- Do NOT generate exam papers or test questions
- Do NOT behave like a quiz system
- Avoid long unnecessary theory blocks
"""
        RESEARCH_PROMPT = """
You are AuLi AI in RESEARCH MODE.

Your job is to act like a research assistant.

Rules:
- Provide deep, structured explanations
- Break answers into sections
- Include comparisons when useful
- Mention sources or known concepts when relevant
- Provide insights, not just definitions
- Use tables if helpful
- Use diagrams in markdown if useful
- Keep language precise and analytical
- Think like an academic researcher or analyst
- Do NOT generate quizzes or exams
"""

        PRACTICE_PROMPT = """
You are AuLi AI in PRACTICE MODE.

Your job is to help the user learn by testing understanding.

Rules:
- Generate questions AND answers together
- Each question must include explanation
- Use a step-by-step learning style
- Format like:
  Q -> Answer -> Explanation
- Keep difficulty medium and adaptive
- Focus on learning reinforcement
- Make it interactive and educational
- Do NOT generate full exam papers
- Do NOT hide answers
"""

        EXAM_PROMPT = """
You are AuLi AI in EXAM MODE.

You generate ONLY question papers.

ABSOLUTE RULES:
- No explanations
- No answers
- No teaching
- No greetings
- No conversational text
- No phrases like "Sure", "Here are", "Let me explain"

OUTPUT MUST START DIRECTLY WITH:

SECTION A: MCQs

FORMAT RULE:
- Strict exam paper format only
- Include sections:
  SECTION A: MCQs (with options A, B, C, D)
  SECTION B: Short Answer Questions
  SECTION C: Long Answer Questions
- Add marks for each question
- Make it realistic like school/university exam

CRITICAL BEHAVIOR:
If user gives a topic (example: "DDL"):
→ Convert it into exam questions only
→ Do NOT explain what the topic is
→ Do NOT define anything

You are not an assistant.
You are an exam paper generator.
"""
        if mode == "practice":
            system_prompt = PRACTICE_PROMPT

        elif mode == "exam":
            system_prompt = EXAM_PROMPT

        elif mode == "study":
            system_prompt = STUDY_PROMPT

        elif mode == "research":
            system_prompt = RESEARCH_PROMPT

 
        # Add special rule for current affairs
        if is_current_question:

            system_prompt += """
- For current affairs questions, answer carefully.
- If uncertain, say information may change over time.
"""
        if is_code_request:

            final_prompt += """

        Important:
        - Separate files properly
        - Use modern UI styling
        - Ensure code is fully runnable
        """
        # Add special rule for coding affairs
        max_output = 5000 if is_code_request else 1200
        # =========================
        # MESSAGES
        # =========================

        messages = [
            {
                "role": "system",
                "content": system_prompt
            },

            *[
                msg for msg in req.history
                if isinstance(msg, dict) and "role" in msg and "content" in msg
            ],

            {
                "role": "user",
                "content": final_prompt
            }
        ]

        print(messages)

        # =========================
        # AI REQUEST
        # =========================

        completion = client.chat.completions.create(
            model="openai/gpt-4.1-mini",
            messages=messages,
            max_tokens=max_output,
            temperature=0.4,
            top_p=0.9
        )

        reply = completion.choices[0].message.content
        # # remove excessive repetition
        # lines = reply.split("\n")

        # cleaned_lines = []

        # previous = ""

        # for line in lines:

        #     if line.strip().lower() != previous.strip().lower():
        #         cleaned_lines.append(line)

        #     previous = line

        # reply = "\n".join(cleaned_lines)

         # ==============================
        # SAVE CHAT TO DATABASE
        # ==============================

        if current_user:

            new_chat = ChatMessage(
                user_id=current_user["user_id"],
                email=current_user["email"],
                user_message=req.message,
                ai_response=reply,
                conversation_id=req.conversation_id
            )

            db.add(new_chat)
            db.commit()

        conversation = None

        if current_user and req.conversation_id:

            conversation = db.query(Conversation).filter(
                Conversation.id == req.conversation_id
            ).first()

            if conversation:

                conversation.updated_at = datetime.utcnow()

                db.commit()


        return {
            "reply": reply,
            "status": "success"
            }

    except Exception as e:
        print("CHAT ERROR:", str(e))
        return {
            "reply": f"Error: {str(e)}"
        }


# ---------------- PDF ENDPOINT ----------------

@app.post("/upload-pdf")
async def upload_pdf(file: UploadFile = File(...)):

    pdf_bytes = await file.read()

    doc = fitz.open(
        stream=pdf_bytes,
        filetype="pdf"
    )

    text = ""

    for page in doc:
        text += page.get_text()

    return {
        "filename": file.filename,
        "text": text[:6000]
    }

@app.get("/chat/history")
def get_chat_history(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):

    messages = db.query(ChatMessage)\
        .filter(ChatMessage.user_id == current_user["user_id"])\
        .order_by(ChatMessage.id.asc())\
        .all()

    return [
        {
            "user_message": m.user_message,
            "ai_response": m.ai_response,
            "created_at": m.created_at
        }
        for m in messages
    ]

# ---------------- PROFILE ENDPOINT ----------------

@app.get("/me")
def get_me(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):

    user = db.query(User).filter(
        User.id == current_user["user_id"]
    ).first()

    if not user:

        return {
            "error": "User not found"
        }

    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "created_at": user.created_at
    }


# ---------------- USAGE TRACKING ----------------

@app.get("/usage-tracking")
def usage_tracking(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):

    chats = db.query(ChatMessage).filter(
        ChatMessage.user_id == current_user["user_id"]
    ).all()

    usage_map = {
        "Mon": 0,
        "Tue": 0,
        "Wed": 0,
        "Thu": 0,
        "Fri": 0,
        "Sat": 0,
        "Sun": 0,
    }

    for chat in chats:

        day = chat.created_at.strftime("%a")

        if day in usage_map:

            usage_map[day] += 1

    max_value = max(usage_map.values()) if chats else 1

    graph_data = []

    for day, value in usage_map.items():

        percentage = int((value / max_value) * 100)

        graph_data.append({
            "day": day,
            "minutes": percentage
        })

    return graph_data

class ConversationRequest(BaseModel):
    message: str


@app.post("/conversation/create")
def create_conversation(
    req: ConversationRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):

    try:

        title_prompt = f"""
        You are a title generator.

        Return ONLY the title.

        Rules:
        - Maximum 4 words
        - No punctuation
        - No quotes
        - No explanations
        - No extra text
        - Output ONLY the final title

        Message:
        {req.message}

        Return format:
        <title>
        """

        completion = client.chat.completions.create(
            model="deepseek/deepseek-chat",
            messages=[
                {
                    "role": "user",
                    "content": title_prompt
                }
            ],
            max_tokens=20,
            temperature=0.3
        )

        title = completion.choices[0].message.content.strip()

        new_conversation = Conversation(
            user_id=current_user["user_id"],
            title=title
        )

        db.add(new_conversation)
        db.commit()
        db.refresh(new_conversation)

        return {
            "conversation_id": new_conversation.id,
            "title": new_conversation.title
        }

    except Exception as e:

        print("TITLE ERROR:", str(e))

        return {
            "error": str(e)
        }


@app.get("/conversations")
def get_conversations(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):


    conversations = db.query(Conversation)\
            .filter(Conversation.user_id == current_user["user_id"])\
            .order_by(
                Conversation.updated_at.desc().nullslast(),
                Conversation.created_at.desc()
            )\
            .all()

    return [
        {
            "id": convo.id,
            "title": convo.title,
            "created_at": convo.created_at
        }
        for convo in conversations
    ]

@app.get("/conversation/{conversation_id}")
def get_single_conversation(
    conversation_id: int,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):

    messages = db.query(ChatMessage)\
        .filter(
            ChatMessage.conversation_id == conversation_id,
            ChatMessage.user_id == current_user["user_id"]
        )\
        .order_by(ChatMessage.id.asc())\
        .all()

    final_messages = []

    for m in messages:

        final_messages.append({
            "role": "user",
            "text": m.user_message
        })

        final_messages.append({
            "role": "ai",
            "text": m.ai_response
        })

    return final_messages

# ---------------- DELETE CONVERSATION ----------------

@app.delete("/conversation/{conversation_id}")
def delete_conversation(
    conversation_id: int,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):

    # find conversation
    conversation = db.query(Conversation).filter(
        Conversation.id == conversation_id,
        Conversation.user_id == current_user["user_id"]
    ).first()

    if not conversation:
        return {
            "error": "Conversation not found"
        }

    # delete all messages first
    db.query(ChatMessage).filter(
        ChatMessage.conversation_id == conversation_id
    ).delete()

    # delete conversation
    db.delete(conversation)

    db.commit()

    return {
        "status": "success",
        "message": "Conversation deleted"
    }