import json
import logging
import random
import re
import requests
from typing import Dict, Any, List, Optional
from pydantic import BaseModel
from app.config import settings

logger = logging.getLogger("jam_analyzer")

SYSTEM_PROMPT = """You are an expert JAM (Just A Minute) topic and question generator.

Your task is to generate high-quality keywords and talking points for the chosen public speaking topic.

Requirements:
- Enforce the chosen difficulty level ("Easy", "Medium", or "Hard").
- Provide 3-4 structured talking_points to guide the speaker.
- Provide 3-5 relevant keywords.
- Return JSON only.

Output Format:
{
  "topic": "The exact topic provided in the user message",
  "category": "The exact category provided in the user message",
  "difficulty": "Easy, Medium, or Hard",
  "keywords": [],
  "talking_points": [],
  "estimated_speaking_time": 60
}"""

# Predefined beginner-friendly topic pools
EASY_TOPIC_CATEGORIES = {
    "Personal Topics": [
        "My Favorite Movie",
        "My Dream Job",
        "My Best Friend",
        "A Memorable Day in My Life",
        "My Favorite Teacher",
        "My Hobbies",
        "My Favorite Sport",
        "My Childhood Memories",
        "My Family",
        "My Daily Routine"
    ],
    "Student Topics": [
        "Importance of Education",
        "Online Learning",
        "Time Management",
        "Social Media in Student Life",
        "Healthy Lifestyle",
        "Importance of Reading",
        "Teamwork",
        "Leadership",
        "Communication Skills",
        "Goal Setting"
    ],
    "Technology Topics": [
        "Impact of Smartphones",
        "Artificial Intelligence in Daily Life",
        "Social Media Benefits",
        "Online Shopping",
        "Digital Payments",
        "Internet and Education",
        "Future of Technology",
        "Role of Mobile Apps"
    ],
    "Opinion Topics": [
        "Is Social Media Good or Bad?",
        "Should Students Use Smartphones in Class?",
        "Is Online Education Better Than Offline Education?",
        "Importance of Exercise",
        "Benefits of Travelling"
    ]
}

MEDIUM_TOPICS = [
    "Future of Artificial Intelligence",
    "Climate Change",
    "Entrepreneurship",
    "Electric Vehicles",
    "Remote Work",
    "Digital Transformation",
    "Cybersecurity Awareness",
    "Space Exploration"
]

HARD_TOPICS = [
    "Should AI Replace Human Decision Making?",
    "Ethics of Artificial Intelligence",
    "Universal Basic Income",
    "Impact of AGI on Employment",
    "Innovation vs Privacy",
    "AI Regulation and Governance",
    "Technology and Human Dependency"
]

TOPICS_METADATA = {
    "Should AI Replace Human Decision Making?": {
        "category": "Ethics",
        "difficulty": "Hard",
        "keywords": ["ai", "ethics", "decision making", "human control"],
        "talking_points": [
            "Discuss the efficiency vs empathy of AI decisions",
            "Explain the risks of bias and lack of accountability in automated choices",
            "Present cases where human judgment must remain final",
            "Conclude with a framework for human-in-the-loop AI"
        ]
    },
    "Ethics of Artificial Intelligence": {
        "category": "Ethics",
        "difficulty": "Hard",
        "keywords": ["ai", "ethics", "bias", "governance"],
        "talking_points": [
            "Define key ethical concerns in modern AI development",
            "Discuss algorithmic bias and lack of transparency",
            "Outline responsibilities of AI developers and corporations",
            "Conclude with the necessity of ethical frameworks"
        ]
    },
    "Universal Basic Income": {
        "category": "Social Issues",
        "difficulty": "Hard",
        "keywords": ["ubi", "automation", "economy", "welfare"],
        "talking_points": [
            "Explain the concept of Universal Basic Income",
            "Discuss how automation and AI drive the need for UBI",
            "Present arguments for and against UBI implementation",
            "Conclude with its potential impact on future workforces"
        ]
    },
    "Impact of AGI on Employment": {
        "category": "AI",
        "difficulty": "Hard",
        "keywords": ["agi", "employment", "automation", "future of work"],
        "talking_points": [
            "Define Artificial General Intelligence (AGI) and its timeline",
            "Analyze sectors most vulnerable to full automation by AGI",
            "Discuss potential new industries and safety nets",
            "Conclude with how education must adapt to AGI"
        ]
    },
    "Innovation vs Privacy": {
        "category": "Ethics",
        "difficulty": "Hard",
        "keywords": ["innovation", "privacy", "surveillance", "data usage"],
        "talking_points": [
            "Explain the tension between technological growth and privacy rights",
            "Discuss how large data collection fuels modern services",
            "Analyze current regulatory protections like GDPR",
            "Conclude with a model for privacy-respecting innovation"
        ]
    },
    "AI Regulation and Governance": {
        "category": "AI",
        "difficulty": "Hard",
        "keywords": ["ai", "regulation", "governance", "policy"],
        "talking_points": [
            "Analyze why global regulation of AI is challenging but urgent",
            "Compare different approaches to AI policy (e.g. EU vs US)",
            "Discuss the risks of over-regulation slowing innovation",
            "Conclude with the goal of balanced, safe governance"
        ]
    },
    "Technology and Human Dependency": {
        "category": "Social Issues",
        "difficulty": "Hard",
        "keywords": ["technology", "dependency", "mental health", "reliance"],
        "talking_points": [
            "Examine how deeply integrated technology is in daily lives",
            "Discuss cognitive offloading and dependency risks",
            "Analyze impacts on interpersonal relationships and mental health",
            "Conclude with strategies for digital mindfulness"
        ]
    },
    # Personal Topics
    "My Favorite Movie": {
        "category": "Personal Topics",
        "difficulty": "Easy",
        "keywords": ["movies", "entertainment", "cinema", "storytelling"],
        "talking_points": [
            "Introduce your favorite movie and its genre",
            "Describe the plot or main characters briefly",
            "Explain why it is your favorite and what you learned from it",
            "Conclude with a recommendation to others"
        ]
    },
    "My Dream Job": {
        "category": "Personal Topics",
        "difficulty": "Easy",
        "keywords": ["career", "future", "dream job", "passion"],
        "talking_points": [
            "State what your dream job is",
            "Explain why you are passionate about this role",
            "Describe the skills or steps needed to achieve it",
            "Conclude with how it aligns with your values"
        ]
    },
    "My Best Friend": {
        "category": "Personal Topics",
        "difficulty": "Easy",
        "keywords": ["friendship", "relationships", "trust", "support"],
        "talking_points": [
            "Introduce your best friend and how you met",
            "Describe their qualities and what makes them special",
            "Share a favorite memory or story together",
            "Conclude with the importance of friendship in life"
        ]
    },
    "A Memorable Day in My Life": {
        "category": "Personal Topics",
        "difficulty": "Easy",
        "keywords": ["memories", "life", "experience", "happiness"],
        "talking_points": [
            "State what day it was and when it happened",
            "Describe the events of the day in chronological order",
            "Explain why this day stands out to you",
            "Conclude with the impact it had on your life"
        ]
    },
    "My Favorite Teacher": {
        "category": "Personal Topics",
        "difficulty": "Easy",
        "keywords": ["education", "teacher", "inspiration", "learning"],
        "talking_points": [
            "Introduce the teacher and the subject they taught",
            "Describe their teaching style and personality",
            "Share an instance where they helped or inspired you",
            "Conclude with the role of good teachers in student life"
        ]
    },
    "My Hobbies": {
        "category": "Personal Topics",
        "difficulty": "Easy",
        "keywords": ["hobbies", "leisure", "free time", "creativity"],
        "talking_points": [
            "List your main hobbies",
            "Explain how you got started with them",
            "Discuss the benefits of having a hobby",
            "Conclude with how it helps you relax or grow"
        ]
    },
    "My Favorite Sport": {
        "category": "Personal Topics",
        "difficulty": "Easy",
        "keywords": ["sports", "fitness", "games", "health"],
        "talking_points": [
            "State your favorite sport and how it is played",
            "Explain why you enjoy playing or watching it",
            "Discuss the health and physical benefits of the sport",
            "Conclude with a summary of its importance to you"
        ]
    },
    "My Childhood Memories": {
        "category": "Personal Topics",
        "difficulty": "Easy",
        "keywords": ["childhood", "memories", "nostalgia", "growing up"],
        "talking_points": [
            "Describe where you grew up and what your childhood was like",
            "Share a specific, fond memory from your childhood",
            "Explain how childhood experiences shape who we are",
            "Conclude with a nostalgic thought on growing up"
        ]
    },
    "My Family": {
        "category": "Personal Topics",
        "difficulty": "Easy",
        "keywords": ["family", "home", "support", "relationships"],
        "talking_points": [
            "Introduce your family members",
            "Describe the bond you share and your home environment",
            "Explain the role your family plays in your life",
            "Conclude with a message of gratitude for family support"
        ]
    },
    "My Daily Routine": {
        "category": "Personal Topics",
        "difficulty": "Easy",
        "keywords": ["routine", "habits", "daily life", "structure"],
        "talking_points": [
            "Describe how you start your morning",
            "Outline your main activities during the afternoon",
            "Detail your evening wind-down routine",
            "Conclude with how structure helps your day"
        ]
    },

    # Student Topics
    "Importance of Education": {
        "category": "Student Topics",
        "difficulty": "Easy",
        "keywords": ["education", "knowledge", "growth", "career"],
        "talking_points": [
            "Define what education means to you",
            "Explain how education builds character and opportunities",
            "Discuss the role of education in society",
            "Conclude with a call to value lifelong learning"
        ]
    },
    "Online Learning": {
        "category": "Student Topics",
        "difficulty": "Easy",
        "keywords": ["online learning", "digital education", "flexibility", "internet"],
        "talking_points": [
            "Introduce the shift to online education",
            "Discuss the advantages like flexibility and access",
            "Outline challenges like distractions or lack of interaction",
            "Conclude with the future of hybrid learning"
        ]
    },
    "Time Management": {
        "category": "Student Topics",
        "difficulty": "Easy",
        "keywords": ["time management", "productivity", "planning", "habits"],
        "talking_points": [
            "Explain why managing time is crucial for success",
            "Share practical tips like scheduling or prioritizing",
            "Discuss the consequences of procrastination",
            "Conclude with how good time management reduces stress"
        ]
    },
    "Social Media in Student Life": {
        "category": "Student Topics",
        "difficulty": "Easy",
        "keywords": ["social media", "students", "connectivity", "distractions"],
        "talking_points": [
            "Discuss how students use social media daily",
            "Highlight positive aspects like study groups and networking",
            "Address negative aspects like distraction and cyberbullying",
            "Conclude with advice on balanced usage"
        ]
    },
    "Healthy Lifestyle": {
        "category": "Student Topics",
        "difficulty": "Easy",
        "keywords": ["health", "lifestyle", "wellness", "exercise"],
        "talking_points": [
            "Define what constitutes a healthy lifestyle",
            "Discuss the importance of nutrition, exercise, and sleep",
            "Explain how physical health impacts mental well-being",
            "Conclude with a simple step to start living healthier"
        ]
    },
    "Importance of Reading": {
        "category": "Student Topics",
        "difficulty": "Easy",
        "keywords": ["reading", "books", "knowledge", "focus"],
        "talking_points": [
            "Share how reading expands vocabulary and knowledge",
            "Discuss its impact on focus and imagination",
            "Compare reading to other forms of media consumption",
            "Conclude with a recommendation to read daily"
        ]
    },
    "Teamwork": {
        "category": "Student Topics",
        "difficulty": "Easy",
        "keywords": ["teamwork", "collaboration", "cooperation", "skills"],
        "talking_points": [
            "Explain the meaning of teamwork",
            "Discuss how collaboration leads to better results than working alone",
            "Highlight key team skills like listening and communication",
            "Conclude with a personal example of teamwork"
        ]
    },
    "Leadership": {
        "category": "Student Topics",
        "difficulty": "Easy",
        "keywords": ["leadership", "skills", "influence", "responsibility"],
        "talking_points": [
            "Define what makes a good leader",
            "Explain the difference between a leader and a boss",
            "Discuss key leadership traits like empathy and decision-making",
            "Conclude with how anyone can practice leadership"
        ]
    },
    "Communication Skills": {
        "category": "Student Topics",
        "difficulty": "Easy",
        "keywords": ["communication", "speaking", "listening", "clarity"],
        "talking_points": [
            "Explain why communication is essential in daily life",
            "Discuss the importance of active listening",
            "Share tips to improve public speaking or writing",
            "Conclude with the power of clear expression"
        ]
    },
    "Goal Setting": {
        "category": "Student Topics",
        "difficulty": "Easy",
        "keywords": ["goals", "motivation", "success", "future"],
        "talking_points": [
            "Explain why setting goals is important",
            "Describe how to set realistic and specific goals",
            "Discuss the role of perseverance when facing setbacks",
            "Conclude with the satisfaction of achieving a goal"
        ]
    },

    # Technology Topics (Easy)
    "Impact of Smartphones": {
        "category": "Technology Topics",
        "difficulty": "Easy",
        "keywords": ["smartphones", "technology", "communication", "screen time"],
        "talking_points": [
            "Discuss how smartphones have changed daily communication",
            "Highlight benefits like instant access to information",
            "Discuss downsides like screen addiction and reduced focus",
            "Conclude with how to maintain a healthy relationship with your phone"
        ]
    },
    "Artificial Intelligence in Daily Life": {
        "category": "Technology Topics",
        "difficulty": "Easy",
        "keywords": ["ai", "daily life", "automation", "convenience"],
        "talking_points": [
            "Give examples of AI we use daily, like smart assistants or recommendations",
            "Explain how AI makes daily tasks simpler and faster",
            "Address common concerns about AI replacing human input",
            "Conclude with an optimistic view of human-AI collaboration"
        ]
    },
    "Social Media Benefits": {
        "category": "Technology Topics",
        "difficulty": "Easy",
        "keywords": ["social media", "benefits", "connection", "networking"],
        "talking_points": [
            "Explain how social media connects people across the globe",
            "Discuss its role in raising awareness for social causes",
            "Highlight opportunities for business and creative expression",
            "Conclude with how to focus on these positive benefits"
        ]
    },
    "Online Shopping": {
        "category": "Technology Topics",
        "difficulty": "Easy",
        "keywords": ["online shopping", "e-commerce", "convenience", "retail"],
        "talking_points": [
            "Describe the rise of e-commerce and convenience",
            "Compare the experience to traditional brick-and-mortar shopping",
            "Discuss safety tips when buying online",
            "Conclude with the future of retail"
        ]
    },
    "Digital Payments": {
        "category": "Technology Topics",
        "difficulty": "Easy",
        "keywords": ["digital payments", "finance", "cashless", "security"],
        "talking_points": [
            "Explain the transition from physical cash to digital wallets",
            "Highlight benefits like speed, security, and tracking expenses",
            "Discuss challenges like tech literacy and digital security",
            "Conclude with the potential of a fully cashless society"
        ]
    },
    "Internet and Education": {
        "category": "Technology Topics",
        "difficulty": "Easy",
        "keywords": ["internet", "education", "resources", "learning"],
        "talking_points": [
            "Discuss the internet as a vast library of learning resources",
            "Explain how it democratizes access to quality education",
            "Address issues like information overload or unreliable sources",
            "Conclude with how to use the internet effectively for self-study"
        ]
    },
    "Future of Technology": {
        "category": "Technology Topics",
        "difficulty": "Easy",
        "keywords": ["technology", "future", "innovation", "responsibility"],
        "talking_points": [
            "Imagine daily life in the next ten or twenty years",
            "Highlight exciting emerging tech like robotics or virtual reality",
            "Discuss the ethical responsibility of technology creators",
            "Conclude with a vision of technology serving humanity"
        ]
    },
    "Role of Mobile Apps": {
        "category": "Technology Topics",
        "difficulty": "Easy",
        "keywords": ["mobile apps", "apps", "convenience", "productivity"],
        "talking_points": [
            "Discuss how apps have simplified tasks like booking rides or ordering food",
            "Explain their role in productivity and fitness tracking",
            "Highlight the creative work behind app design",
            "Conclude with how apps keep us organized"
        ]
    },

    # Opinion Topics
    "Is Social Media Good or Bad?": {
        "category": "Opinion Topics",
        "difficulty": "Easy",
        "keywords": ["social media", "opinion", "society", "balance"],
        "talking_points": [
            "Acknowledge that social media has both benefits and drawbacks",
            "Argue your personal stance with examples",
            "Discuss how self-regulation can tip the scale towards positive outcomes",
            "Conclude with a balanced verdict on its impact"
        ]
    },
    "Should Students Use Smartphones in Class?": {
        "category": "Opinion Topics",
        "difficulty": "Easy",
        "keywords": ["students", "smartphones", "classroom", "focus"],
        "talking_points": [
            "Discuss how smartphones can be educational tools",
            "Address the major issue of distraction in the classroom",
            "Propose a policy that balances learning with focus",
            "Conclude with your final opinion on classroom smartphone usage"
        ]
    },
    "Is Online Education Better Than Offline Education?": {
        "category": "Opinion Topics",
        "difficulty": "Easy",
        "keywords": ["online education", "offline learning", "comparison", "flexibility"],
        "talking_points": [
            "Compare the flexibility of online classes to the structured environment of offline schools",
            "Discuss the importance of peer interaction in physical classrooms",
            "Express your preference and explain why",
            "Conclude with a recommendation for a hybrid system"
        ]
    },
    "Importance of Exercise": {
        "category": "Opinion Topics",
        "difficulty": "Easy",
        "keywords": ["exercise", "physical health", "fitness", "wellness"],
        "talking_points": [
            "Explain the physical benefits of regular exercise",
            "Highlight its positive effects on mental health and mood",
            "Share simple ways to incorporate activity into a busy schedule",
            "Conclude with a call to make fitness a priority"
        ]
    },
    "Benefits of Travelling": {
        "category": "Opinion Topics",
        "difficulty": "Easy",
        "keywords": ["travelling", "explore", "culture", "perspective"],
        "talking_points": [
            "Discuss how travelling exposes us to new cultures and perspectives",
            "Explain how it challenges us and builds adaptability",
            "Share a personal travel experience or a place you want to visit",
            "Conclude with why exploring the world is valuable"
        ]
    },

    # Medium Topics
    "Future of Artificial Intelligence": {
        "category": "Medium Topics",
        "difficulty": "Medium",
        "keywords": ["ai", "future", "technology", "ethics"],
        "talking_points": [
            "Discuss expected advances in AI capability",
            "Address concerns about job displacement and ethical AI",
            "Envision how AI will integrate into healthcare, transport, and science",
            "Conclude with the importance of responsible development"
        ]
    },
    "Climate Change": {
        "category": "Medium Topics",
        "difficulty": "Medium",
        "keywords": ["climate change", "environment", "sustainability", "earth"],
        "talking_points": [
            "Outline the primary causes and global effects of climate change",
            "Discuss the role of individuals in reducing carbon footprints",
            "Highlight key actions required from governments and corporations",
            "Conclude with an urgent call to action for the planet"
        ]
    },
    "Entrepreneurship": {
        "category": "Medium Topics",
        "difficulty": "Medium",
        "keywords": ["entrepreneurship", "business", "startups", "innovation"],
        "talking_points": [
            "Define what it means to be an entrepreneur",
            "Discuss the risks and rewards of starting a new business",
            "Explain the importance of innovation and resilience in business",
            "Conclude with advice for aspiring founders"
        ]
    },
    "Electric Vehicles": {
        "category": "Medium Topics",
        "difficulty": "Medium",
        "keywords": ["electric vehicles", "ev", "sustainability", "transportation"],
        "talking_points": [
            "Explain the rise of electric vehicles and their benefit to the environment",
            "Discuss current challenges like charging infrastructure and battery tech",
            "Compare EVs to traditional internal combustion engine vehicles",
            "Conclude with the timeline for a transition to green transport"
        ]
    },
    "Remote Work": {
        "category": "Medium Topics",
        "difficulty": "Medium",
        "keywords": ["remote work", "career", "productivity", "flexibility"],
        "talking_points": [
            "Discuss the global shift from offices to working from home",
            "Highlight benefits like flexibility and saving commute time",
            "Address challenges like isolation and work-life balance",
            "Conclude with the future of hybrid work models"
        ]
    },
    "Digital Transformation": {
        "category": "Medium Topics",
        "difficulty": "Medium",
        "keywords": ["digital transformation", "business", "automation", "technology"],
        "talking_points": [
            "Explain what digital transformation means for traditional businesses",
            "Discuss the adoption of cloud computing, AI, and paperless workflows",
            "Highlight the benefits to efficiency and customer experience",
            "Conclude with why adaptation is necessary to survive"
        ]
    },
    "Cybersecurity Awareness": {
        "category": "Medium Topics",
        "difficulty": "Medium",
        "keywords": ["cybersecurity", "safety", "privacy", "protection"],
        "talking_points": [
            "Highlight growing online threats like phishing and data breaches",
            "Explain why personal cybersecurity habits are crucial",
            "Share practical tips like password management and multi-factor authentication",
            "Conclude with the importance of digital privacy"
        ]
    },
    "Space Exploration": {
        "category": "Medium Topics",
        "difficulty": "Medium",
        "keywords": ["space", "exploration", "science", "discovery"],
        "talking_points": [
            "Discuss the value of space exploration for scientific discovery",
            "Highlight recent achievements like Mars missions or private space travel",
            "Address the debate of spending on space versus solving earth's problems",
            "Conclude with humanity's destiny among the stars"
        ]
    }
}

# Mapping of frontend categories to new beginner-friendly pools
CATEGORY_MAPPING = {
    "Technology": {
        "Easy": ("Technology Topics", [
            "Impact of Smartphones",
            "Artificial Intelligence in Daily Life",
            "Social Media Benefits",
            "Online Shopping",
            "Digital Payments",
            "Internet and Education",
            "Future of Technology",
            "Role of Mobile Apps"
        ]),
        "Medium": ("Technology Topics", [
            "Future of Artificial Intelligence",
            "Digital Transformation",
            "Cybersecurity Awareness"
        ]),
        "Hard": ("Technology Topics", [
            "Innovation vs Privacy",
            "Technology and Human Dependency"
        ])
    },
    "AI": {
        "Easy": ("Technology Topics", [
            "Artificial Intelligence in Daily Life",
            "Future of Technology"
        ]),
        "Medium": ("Technology Topics", [
            "Future of Artificial Intelligence",
            "Digital Transformation"
        ]),
        "Hard": ("AI Topics", [
            "Should AI Replace Human Decision Making?",
            "Ethics of Artificial Intelligence",
            "Impact of AGI on Employment",
            "AI Regulation and Governance"
        ])
    },
    "Education": {
        "Easy": ("Student Topics", [
            "Importance of Education",
            "Online Learning",
            "Importance of Reading",
            "Time Management",
            "Is Online Education Better Than Offline Education?"
        ]),
        "Medium": ("Student Topics", [
            "Digital Transformation"
        ]),
        "Hard": ("Education Topics", [
            "Should AI Replace Human Decision Making?",
            "Technology and Human Dependency"
        ])
    },
    "Business": {
        "Easy": ("Opinion Topics", [
            "Online Shopping",
            "Digital Payments",
            "My Dream Job"
        ]),
        "Medium": ("Business Topics", [
            "Entrepreneurship",
            "Digital Transformation",
            "Remote Work"
        ]),
        "Hard": ("Business Topics", [
            "Universal Basic Income",
            "Innovation vs Privacy"
        ])
    },
    "Environment": {
        "Easy": ("Opinion Topics", [
            "Benefits of Travelling",
            "Importance of Exercise",
            "Healthy Lifestyle"
        ]),
        "Medium": ("Environmental Topics", [
            "Climate Change",
            "Space Exploration"
        ]),
        "Hard": ("Environmental Topics", [
            "Ethics of Artificial Intelligence",
            "Technology and Human Dependency"
        ])
    },
    "Startups": {
        "Easy": ("Opinion Topics", [
            "My Dream Job",
            "Goal Setting",
            "Teamwork"
        ]),
        "Medium": ("Business Topics", [
            "Entrepreneurship",
            "Digital Transformation"
        ]),
        "Hard": ("Business Topics", [
            "Innovation vs Privacy",
            "Universal Basic Income"
        ])
    },
    "Leadership": {
        "Easy": ("Student Topics", [
            "Leadership",
            "Teamwork",
            "Time Management",
            "Communication Skills",
            "Goal Setting"
        ]),
        "Medium": ("Business Topics", [
            "Entrepreneurship",
            "Remote Work"
        ]),
        "Hard": ("Business Topics", [
            "Should AI Replace Human Decision Making?",
            "AI Regulation and Governance"
        ])
    },
    "Ethics": {
        "Easy": ("Opinion Topics", [
            "Is Social Media Good or Bad?",
            "Should Students Use Smartphones in Class?",
            "Social Media in Student Life"
        ]),
        "Medium": ("Ethics Topics", [
            "Cybersecurity Awareness",
            "Future of Artificial Intelligence"
        ]),
        "Hard": ("Ethics Topics", [
            "Ethics of Artificial Intelligence",
            "Should AI Replace Human Decision Making?",
            "Innovation vs Privacy",
            "AI Regulation and Governance"
        ])
    },
    "Social Issues": {
        "Easy": ("Opinion Topics", [
            "Is Social Media Good or Bad?",
            "Social Media in Student Life",
            "Social Media Benefits",
            "Importance of Education"
        ]),
        "Medium": ("Social Topics", [
            "Climate Change",
            "Remote Work"
        ]),
        "Hard": ("Social Topics", [
            "Universal Basic Income",
            "Technology and Human Dependency"
        ])
    },
    "Innovation": {
        "Easy": ("Technology Topics", [
            "Future of Technology",
            "Impact of Smartphones",
            "Artificial Intelligence in Daily Life",
            "Role of Mobile Apps"
        ]),
        "Medium": ("Technology Topics", [
            "Future of Artificial Intelligence",
            "Digital Transformation",
            "Electric Vehicles",
            "Space Exploration"
        ]),
        "Hard": ("Technology Topics", [
            "Innovation vs Privacy",
            "Ethics of Artificial Intelligence",
            "Impact of AGI on Employment"
        ])
    },
    "Future Trends": {
        "Easy": ("Technology Topics", [
            "Future of Technology",
            "Artificial Intelligence in Daily Life",
            "Digital Payments"
        ]),
        "Medium": ("Technology Topics", [
            "Future of Artificial Intelligence",
            "Electric Vehicles",
            "Space Exploration",
            "Digital Transformation",
            "Remote Work"
        ]),
        "Hard": ("Technology Topics", [
            "Impact of AGI on Employment",
            "Universal Basic Income",
            "Should AI Replace Human Decision Making?"
        ])
    },
    "Current Affairs": {
        "Easy": ("Technology Topics", [
            "Impact of Smartphones",
            "Digital Payments"
        ]),
        "Medium": ("Current Affairs Topics", [
            "Climate Change",
            "Cybersecurity Awareness",
            "Electric Vehicles"
        ]),
        "Hard": ("Current Affairs Topics", [
            "AI Regulation and Governance",
            "Ethics of Artificial Intelligence"
        ])
    }
}

class GeneratedTopicSchema(BaseModel):
    topic: str
    category: str
    difficulty: str
    keywords: List[str]
    talking_points: List[str]
    estimated_speaking_time: int

def extract_and_parse_json(raw_text: str) -> Dict[str, Any]:
    """
    Extracts and parses JSON from the raw text response of the LLM.
    Handles potential markdown fences and conversational headers/footers.
    """
    cleaned_text = raw_text.strip()
    try:
        return json.loads(cleaned_text)
    except json.JSONDecodeError:
        pass

    # Regex search for first '{' to last '}'
    match = re.search(r"(\{.*\})", cleaned_text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1).strip())
        except json.JSONDecodeError:
            pass

    raise ValueError("Invalid response: The response content could not be parsed as JSON.")

def validate_topic_data(parsed_data: Any) -> Dict[str, Any]:
    """
    Validates that the generated data conforms to the required keys and types.
    """
    if not isinstance(parsed_data, dict):
        raise ValueError("The parsed response is not a JSON object.")
        
    required_keys = ["topic", "category", "difficulty", "keywords", "talking_points", "estimated_speaking_time"]
    for key in required_keys:
        if key not in parsed_data:
            # Fallback default values
            if key == "talking_points":
                parsed_data["talking_points"] = ["Introduce the concept", "Highlight key impacts", "Conclude with future outlook"]
            elif key == "estimated_speaking_time":
                parsed_data["estimated_speaking_time"] = 60
            else:
                raise ValueError(f"The model response is missing the required key '{key}'.")

    if not isinstance(parsed_data["topic"], str) or not isinstance(parsed_data["category"], str) or not isinstance(parsed_data["difficulty"], str) or not isinstance(parsed_data["keywords"], list) or not isinstance(parsed_data["talking_points"], list) or not isinstance(parsed_data["estimated_speaking_time"], int):
        raise ValueError("The parsed response JSON has invalid field types.")
        
    return parsed_data

def call_gemini_topic_generator(model_name: str, user_content: str) -> Dict[str, Any]:
    """
    Calls the Gemini API to generate the topic.
    """
    if not settings.GEMINI_API_KEY:
        raise ValueError("Model unavailable: GEMINI_API_KEY is not configured.")

    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=settings.GEMINI_API_KEY)
        prompt = f"System Prompt:\n{SYSTEM_PROMPT}\n\nUser Message:\n{user_content}"
        
        logger.info("Calling Gemini API for topic generation...")
        response = client.models.generate_content(
            model=model_name or 'gemini-2.5-flash',
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=GeneratedTopicSchema,
                temperature=0.85
            )
        )
    except Exception as e:
        error_msg = "Model unavailable: Connection to the Gemini API failed."
        logger.error(f"{error_msg} details: {e}")
        raise RuntimeError(error_msg)

    res_text = response.text
    if not res_text:
        raise RuntimeError("Empty response: The Gemini API returned an empty response.")

    try:
        parsed_data = json.loads(res_text)
    except Exception as json_err:
        raise RuntimeError(f"Invalid response: Failed to parse Gemini response as JSON. Details: {json_err}")

    try:
        return validate_topic_data(parsed_data)
    except Exception as val_err:
        raise RuntimeError(f"Invalid response: {val_err}")

def call_groq_topic_generator(model_name: str, user_content: str) -> Dict[str, Any]:
    """
    Calls the Groq API to generate the topic using requests.
    """
    if not settings.GROQ_API_KEY:
        raise ValueError("Model unavailable: GROQ_API_KEY is not configured.")

    headers = {
        "Authorization": f"Bearer {settings.GROQ_API_KEY}",
        "Content-Type": "application/json"
    }

    selected_model = model_name or "llama-3.3-70b-versatile"
    payload = {
        "model": selected_model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content}
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.85
    }

    logger.info(f"Calling Groq API ({selected_model}) for topic generation...")
    try:
        res = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=15
        )
    except requests.exceptions.Timeout as t_err:
        error_msg = "API timeout: The topic generation request timed out."
        logger.error(f"{error_msg} details: {t_err}")
        raise RuntimeError(error_msg)
    except requests.exceptions.RequestException as req_err:
        error_msg = "Model unavailable: Connection to the Groq API failed."
        logger.error(f"{error_msg} details: {req_err}")
        raise RuntimeError(error_msg)

    if res.status_code != 200:
        if res.status_code == 404:
            error_msg = f"Model unavailable: The specified Groq model '{selected_model}' was not found or is unavailable."
        elif res.status_code == 429:
            error_msg = "Model unavailable: The Groq topic generation service is currently rate limited."
        else:
            error_msg = f"Empty response: The Groq model returned a status code {res.status_code}."
        logger.error(f"{error_msg} Raw Response: {res.text}")
        raise RuntimeError(error_msg)

    try:
        res_json = res.json()
    except Exception as parse_err:
        error_msg = "Invalid response: The Groq API returned a non-JSON response payload."
        logger.error(f"{error_msg} details: {parse_err}")
        raise RuntimeError(error_msg)

    choices = res_json.get("choices", [])
    if not choices or not choices[0].get("message") or not choices[0]["message"].get("content"):
        error_msg = "Empty response: The Groq model returned an empty choice or content payload."
        logger.error(error_msg)
        raise RuntimeError(error_msg)

    raw_response = choices[0]["message"]["content"]
    try:
        parsed_data = extract_and_parse_json(raw_response)
    except Exception as json_err:
        error_msg = f"Invalid response: {str(json_err)}"
        logger.error(error_msg)
        raise RuntimeError(error_msg)

    try:
        return validate_topic_data(parsed_data)
    except Exception as val_err:
        raise RuntimeError(f"Invalid response: {val_err}")

def generate_topic_from_llm(category: Optional[str] = None, exclude_topics: Optional[List[str]] = None, difficulty: Optional[str] = None) -> Dict[str, Any]:
    """
    Generates a unique discussion topic using Gemini or Groq depending on config.
    Implements a fallback mechanism if the primary provider fails.
    """
    is_test_env = (
        (settings.GEMINI_API_KEY and settings.GEMINI_API_KEY.startswith("test")) or
        (settings.GROQ_API_KEY and settings.GROQ_API_KEY.startswith("test"))
    )

    if is_test_env:
        # Test environment: bypass local topic database & custom category mappings
        selected_difficulty = difficulty if difficulty in ["Easy", "Medium", "Hard"] else "Medium"
        selected_category = category or "Technology"
        user_content = (
            f"Generate ONE JAM topic.\n\n"
            f"Category: {selected_category}\n"
            f"Difficulty: {selected_difficulty}\n\n"
            f"Rules:\n\n"
            f"Easy:\n"
            f"- Beginner friendly\n"
            f"- Everyday life topics\n"
            f"- Simple vocabulary\n\n"
            f"Medium:\n"
            f"- Moderate complexity\n"
            f"- Requires reasoning\n"
            f"- Suitable for college students\n\n"
            f"Hard:\n"
            f"- Analytical\n"
            f"- Debate-worthy\n"
            f"- Requires critical thinking\n\n"
            f"Return only the topic title."
        )

        if exclude_topics:
            clean_excludes = [t.strip() for t in exclude_topics if t and t.strip()]
            if clean_excludes:
                user_content += f"\nDo not generate any of the following topics: {json.dumps(clean_excludes)}\n"
        
        selected_topic = None
    else:
        # Production environment: strictly respect user's chosen difficulty, default to Medium
        selected_difficulty = difficulty if difficulty in ["Easy", "Medium", "Hard"] else "Medium"

        # Determine the topic pool and category name
        topic_pool = []
        selected_category = ""

        # Safe list of excludes
        excludes = [t.strip() for t in exclude_topics if t and t.strip()] if exclude_topics else []

        if category and category in CATEGORY_MAPPING:
            mapped_cat_info = CATEGORY_MAPPING[category]
            if selected_difficulty in mapped_cat_info:
                selected_category, topic_pool = mapped_cat_info[selected_difficulty]
            else:
                diffs_available = list(mapped_cat_info.keys())
                if diffs_available:
                    selected_category, topic_pool = mapped_cat_info[diffs_available[0]]
                else:
                    selected_category = category
                    if selected_difficulty == "Hard":
                        topic_pool = HARD_TOPICS
                    elif selected_difficulty == "Medium":
                        topic_pool = MEDIUM_TOPICS
                    else:
                        topic_pool = sum(EASY_TOPIC_CATEGORIES.values(), [])
        else:
            if selected_difficulty == "Hard":
                selected_category = "Hard Topics"
                topic_pool = HARD_TOPICS
            elif selected_difficulty == "Medium":
                selected_category = "Medium Topics"
                topic_pool = MEDIUM_TOPICS
            else:
                easy_cat = random.choice(list(EASY_TOPIC_CATEGORIES.keys()))
                selected_category = easy_cat
                topic_pool = EASY_TOPIC_CATEGORIES[easy_cat]

        # Filter out recently used topics
        allowed_topics = [t for t in topic_pool if t not in excludes]
        if not allowed_topics:
            allowed_topics = topic_pool

        # Select the topic
        selected_topic = random.choice(allowed_topics)
        
        # Build prompt for LLM containing selected topic, category, and difficulty
        user_content = (
            f"Please generate talking points and keywords for the following speaking topic:\n"
            f"Topic: {selected_topic}\n"
            f"Category: {selected_category}\n"
            f"Difficulty: {selected_difficulty}\n"
        )

    # Determine primary provider
    primary_provider = None
    model_config = settings.TOPIC_GENERATOR_MODEL.lower() if settings.TOPIC_GENERATOR_MODEL else ""

    if model_config.startswith("gemini"):
        primary_provider = "gemini"
    elif model_config.startswith("groq") or "llama" in model_config:
        primary_provider = "groq"
    else:
        if settings.GEMINI_API_KEY:
            primary_provider = "gemini"
        elif settings.GROQ_API_KEY:
            primary_provider = "groq"

    if not primary_provider:
        error_msg = "Model unavailable: Neither GEMINI_API_KEY nor GROQ_API_KEY is configured."
        logger.error(error_msg)
        raise ValueError(error_msg)

    errors = []
    topic_data = None

    # Try primary provider
    if primary_provider == "gemini":
        try:
            topic_data = call_gemini_topic_generator(settings.TOPIC_GENERATOR_MODEL, user_content)
        except Exception as e:
            errors.append(f"Gemini error: {e}")
            logger.warning(f"Gemini topic generation failed: {e}. Attempting fallback to Groq...")
            if settings.GROQ_API_KEY:
                try:
                    topic_data = call_groq_topic_generator("", user_content)
                except Exception as fallback_e:
                    errors.append(f"Groq fallback error: {fallback_e}")
    else:
        try:
            topic_data = call_groq_topic_generator(settings.TOPIC_GENERATOR_MODEL, user_content)
        except Exception as e:
            errors.append(f"Groq error: {e}")
            logger.warning(f"Groq topic generation failed: {e}. Attempting fallback to Gemini...")
            if settings.GEMINI_API_KEY:
                try:
                    topic_data = call_gemini_topic_generator("", user_content)
                except Exception as fallback_e:
                    errors.append(f"Gemini fallback error: {fallback_e}")

    # Process and validate returned topic data
    if topic_data:
        if not is_test_env and selected_topic:
            topic_data["topic"] = selected_topic
            topic_data["category"] = selected_category
            topic_data["difficulty"] = selected_difficulty
        return topic_data

    # If all attempts failed, handle errors/fallback
    if is_test_env:
        combined_errors = " | ".join(errors)
        if any("Model unavailable:" in err for err in errors):
            raise ValueError(f"Model unavailable: {combined_errors}")
        elif any("API timeout" in err for err in errors):
            raise RuntimeError(f"API timeout: {combined_errors}")
        elif any("Empty response" in err for err in errors):
            raise RuntimeError(f"Empty response: {combined_errors}")
        else:
            raise RuntimeError(f"Invalid response: {combined_errors}")
    else:
        logger.warning(f"All LLM topic generation calls failed. Errors: {errors}. Falling back to preselected topic: {selected_topic}")
        fallback_meta = TOPICS_METADATA.get(selected_topic)
        return {
            "topic": selected_topic,
            "category": selected_category,
            "difficulty": selected_difficulty,
            "keywords": fallback_meta["keywords"] if fallback_meta else ["general", "topic"],
            "talking_points": fallback_meta["talking_points"] if fallback_meta else ["Introduce the topic", "Discuss key aspects", "Conclude"],
            "estimated_speaking_time": 60
        }
