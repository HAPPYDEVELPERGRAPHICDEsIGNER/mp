"""
AI Code Generation Service.
Supports optional Google Gemini or OpenAI API via server-side environment variables.
When no API key is configured, operates in a high-fidelity local DEMO MODE
with deterministic, production-grade templates and algorithmic generators.
"""
import os
import re
import logging
from typing import Dict, Any, Optional
import httpx

logger = logging.getLogger("copilot.ai_service")

# Supported programming languages
SUPPORTED_LANGUAGES = ["Python", "C++", "Java", "JavaScript"]

def is_ai_configured() -> bool:
    """Checks if an external AI LLM provider is configured via environment variables."""
    return bool(os.getenv("GEMINI_API_KEY") or os.getenv("OPENAI_API_KEY"))

def get_ai_provider_info() -> Dict[str, Any]:
    """Returns provider status without exposing secrets."""
    if os.getenv("GEMINI_API_KEY"):
        return {"configured": True, "provider": "Google Gemini", "model": os.getenv("GEMINI_MODEL", "gemini-1.5-flash")}
    if os.getenv("OPENAI_API_KEY"):
        return {"configured": True, "provider": "OpenAI", "model": os.getenv("OPENAI_MODEL", "gpt-4o-mini")}
    return {"configured": False, "provider": "Local Heuristic Engine", "model": "Deterministic Code Synthesizer (Demo Mode)"}

async def generate_code(prompt: str, language: str, style: str = "standard") -> Dict[str, Any]:
    """
    Generates code based on the prompt and language.
    If an API key is available, calls the LLM provider.
    Otherwise, returns deterministic, high-quality starter code.
    """
    cleaned_prompt = prompt.strip()
    if not cleaned_prompt:
        raise ValueError("Requirement prompt cannot be empty.")
    if language not in SUPPORTED_LANGUAGES:
        raise ValueError(f"Language '{language}' is not supported. Must be one of {SUPPORTED_LANGUAGES}")

    gemini_key = os.getenv("GEMINI_API_KEY")
    openai_key = os.getenv("OPENAI_API_KEY")

    if gemini_key:
        try:
            return await _generate_with_gemini(cleaned_prompt, language, gemini_key, style)
        except Exception as e:
            logger.warning("Gemini generation failed (%s); falling back to local generator", e)
            fallback = _generate_local_deterministic(cleaned_prompt, language, style)
            fallback["warning"] = f"LLM request failed ({str(e)}). Returned offline fallback."
            return fallback

    if openai_key:
        try:
            return await _generate_with_openai(cleaned_prompt, language, openai_key, style)
        except Exception as e:
            logger.warning("OpenAI generation failed (%s); falling back to local generator", e)
            fallback = _generate_local_deterministic(cleaned_prompt, language, style)
            fallback["warning"] = f"LLM request failed ({str(e)}). Returned offline fallback."
            return fallback

    # Default: Local High-Fidelity Demo Mode
    return _generate_local_deterministic(cleaned_prompt, language, style)

async def _generate_with_gemini(prompt: str, language: str, api_key: str, style: str) -> Dict[str, Any]:
    """Invokes Google Gemini API safely via backend HTTP request."""
    model = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"

    system_instruction = (
        f"You are an expert software engineer assistant. Generate clean, robust, idiomatically correct {language} code. "
        f"Style: {style}. Include comments explaining edge cases, complexity, and a working usage demonstration. "
        "Return your answer clearly, placing the main source code in Markdown code blocks."
    )

    payload = {
        "contents": [
            {"role": "user", "parts": [{"text": f"{system_instruction}\n\nRequirement: {prompt}"}]}
        ],
        "generationConfig": {
            "temperature": 0.2,
            "maxOutputTokens": 2048,
        }
    }

    async with httpx.AsyncClient(timeout=25.0) as client:
        resp = await client.post(url, json=payload)
        resp.raise_for_status()
        data = resp.json()

    candidates = data.get("candidates", [])
    if not candidates:
        raise RuntimeError("No generation candidates returned from Gemini.")

    raw_text = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")
    code = _extract_code_block(raw_text, language)

    return {
        "mode": "LIVE AI",
        "provider": "Google Gemini",
        "model": model,
        "language": language,
        "code": code,
        "explanation": raw_text,
        "message": f"Successfully generated using {model}."
    }

async def _generate_with_openai(prompt: str, language: str, api_key: str, style: str) -> Dict[str, Any]:
    """Invokes OpenAI-compatible API safely via backend HTTP request."""
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1") + "/chat/completions"

    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": f"You are an expert AI software engineer. Generate production-ready {language} code adhering to best practices and {style} style."
            },
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.2,
        "max_tokens": 2048
    }

    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    async with httpx.AsyncClient(timeout=25.0) as client:
        resp = await client.post(url, json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()

    raw_text = data["choices"][0]["message"]["content"]
    code = _extract_code_block(raw_text, language)

    return {
        "mode": "LIVE AI",
        "provider": "OpenAI",
        "model": model,
        "language": language,
        "code": code,
        "explanation": raw_text,
        "message": f"Successfully generated using {model}."
    }

def _extract_code_block(text: str, language: str) -> str:
    """Extracts code block from markdown or returns original text if not fenced."""
    pattern = r"```(?:[a-zA-Z0-9#+]+)?\s*\n([\s\S]*?)```"
    matches = re.findall(pattern, text)
    if matches:
        return matches[0].strip()
    return text.strip()

def _generate_local_deterministic(prompt: str, language: str, style: str) -> Dict[str, Any]:
    """
    Deterministic rule-based code generator for demo mode.
    Provides complete, working, well-commented implementations for common DSA,
    APIs, utilities, and problem archetypes.
    """
    p = prompt.lower()

    # 1. Factorial
    if "factorial" in p:
        if language == "Python":
            code = '''def factorial(n: int) -> int:
    """
    Calculate the factorial of a non-negative integer n.
    Time Complexity: O(n) | Space Complexity: O(1)
    """
    if not isinstance(n, int):
        raise TypeError("n must be an integer.")
    if n < 0:
        raise ValueError("n must be a non-negative integer.")
    
    result = 1
    for i in range(2, n + 1):
        result *= i
    return result

# Example demonstration
if __name__ == "__main__":
    test_cases = [0, 1, 5, 10]
    for val in test_cases:
        print(f"factorial({val}) = {factorial(val)}")
'''
        elif language == "JavaScript":
            code = '''/**
 * Calculate the factorial of a non-negative integer.
 * @param {number} n
 * @returns {number}
 */
function factorial(n) {
  if (!Number.isInteger(n) || n < 0) {
    throw new TypeError("n must be a non-negative integer.");
  }
  let result = 1;
  for (let i = 2; i <= n; i++) {
    result *= i;
  }
  return result;
}

// Example demonstration
[0, 1, 5, 10].forEach(val => {
  console.log(`factorial(${val}) = ${factorial(val)}`);
});
'''
        elif language == "C++":
            code = '''#include <iostream>
#include <stdexcept>

/**
 * Calculate the factorial of a non-negative integer.
 * Time Complexity: O(n) | Space Complexity: O(1)
 */
unsigned long long factorial(int n) {
    if (n < 0) {
        throw std::invalid_argument("n must be non-negative.");
    }
    unsigned long long result = 1;
    for (int i = 2; i <= n; ++i) {
        result *= i;
    }
    return result;
}

int main() {
    int testValues[] = {0, 1, 5, 10};
    for (int val : testValues) {
        std::cout << "factorial(" << val << ") = " << factorial(val) << std::endl;
    }
    return 0;
}
'''
        else: # Java
            code = '''public class FactorialCalculator {
    /**
     * Calculate the factorial of a non-negative integer.
     * Time Complexity: O(n) | Space Complexity: O(1)
     */
    public static long factorial(int n) {
        if (n < 0) {
            throw new IllegalArgumentException("n must be non-negative.");
        }
        long result = 1;
        for (int i = 2; i <= n; i++) {
            result *= i;
        }
        return result;
    }

    public static void main(String[] args) {
        int[] testCases = {0, 1, 5, 10};
        for (int val : testCases) {
            System.out.println("factorial(" + val + ") = " + factorial(val));
        }
    }
}
'''
        return {
            "mode": "DEMO MODE",
            "provider": "Local Template Synthesizer",
            "model": "Deterministic DSA Template",
            "language": language,
            "code": code,
            "explanation": "Generated a verified iterative factorial function with input validation, type constraints, and demonstration test cases.",
            "message": "Deterministic sample output. Configure GEMINI_API_KEY or OPENAI_API_KEY in .env for custom prompt synthesis."
        }

    # 2. Fibonacci
    if "fibonacci" in p or "fib" in p:
        if language == "Python":
            code = '''def fibonacci(n: int) -> int:
    """
    Returns the n-th Fibonacci number using O(1) space iterative dynamic programming.
    F(0) = 0, F(1) = 1, F(n) = F(n-1) + F(n-2).
    """
    if not isinstance(n, int) or n < 0:
        raise ValueError("n must be a non-negative integer.")
    if n <= 1:
        return n
    
    prev, curr = 0, 1
    for _ in range(2, n + 1):
        prev, curr = curr, prev + curr
    return curr

if __name__ == "__main__":
    for i in range(10):
        print(f"F({i}) = {fibonacci(i)}")
'''
        elif language == "JavaScript":
            code = '''function fibonacci(n) {
  if (!Number.isInteger(n) || n < 0) {
    throw new Error("n must be a non-negative integer.");
  }
  if (n <= 1) return n;
  let prev = 0, curr = 1;
  for (let i = 2; i <= n; i++) {
    const next = prev + curr;
    prev = curr;
    curr = next;
  }
  return curr;
}

for (let i = 0; i < 10; i++) {
  console.log(`F(${i}) = ${fibonacci(i)}`);
}
'''
        elif language == "C++":
            code = '''#include <iostream>
#include <stdexcept>

long long fibonacci(int n) {
    if (n < 0) throw std::invalid_argument("n must be non-negative.");
    if (n <= 1) return n;
    long long prev = 0, curr = 1;
    for (int i = 2; i <= n; ++i) {
        long long next = prev + curr;
        prev = curr;
        curr = next;
    }
    return curr;
}

int main() {
    for (int i = 0; i < 10; ++i) {
        std::cout << "F(" << i << ") = " << fibonacci(i) << "\\n";
    }
    return 0;
}
'''
        else: # Java
            code = '''public class Fibonacci {
    public static long fibonacci(int n) {
        if (n < 0) throw new IllegalArgumentException("n must be non-negative.");
        if (n <= 1) return n;
        long prev = 0, curr = 1;
        for (int i = 2; i <= n; i++) {
            long next = prev + curr;
            prev = curr;
            curr = next;
        }
        return curr;
    }

    public static void main(String[] args) {
        for (int i = 0; i < 10; i++) {
            System.out.println("F(" + i + ") = " + fibonacci(i));
        }
    }
}
'''
        return {
            "mode": "DEMO MODE",
            "provider": "Local Template Synthesizer",
            "model": "Deterministic DSA Template",
            "language": language,
            "code": code,
            "explanation": "Generated an optimal O(n) time, O(1) space iterative Fibonacci algorithm with edge case handling.",
            "message": "Deterministic sample output. Configure GEMINI_API_KEY in .env for custom AI generation."
        }

    # 3. Binary Search
    if "binary search" in p or "search" in p:
        if language == "Python":
            code = '''from typing import List, Optional

def binary_search(arr: List[int], target: int) -> Optional[int]:
    """
    Search for target in sorted array arr using Binary Search.
    Returns index if found, or None if not present.
    Time Complexity: O(log n) | Space Complexity: O(1)
    """
    left, right = 0, len(arr) - 1
    
    while left <= right:
        mid = left + (right - left) // 2  # Avoids integer overflow
        if arr[mid] == target:
            return mid
        elif arr[mid] < target:
            left = mid + 1
        else:
            right = mid - 1
            
    return None

if __name__ == "__main__":
    nums = [1, 3, 5, 7, 9, 11, 15, 20]
    print(f"Search 7: {binary_search(nums, 7)}")    # Expected: 3
    print(f"Search 4: {binary_search(nums, 4)}")    # Expected: None
'''
        elif language == "JavaScript":
            code = '''function binarySearch(arr, target) {
  let left = 0;
  let right = arr.length - 1;
  while (left <= right) {
    const mid = Math.floor(left + (right - left) / 2);
    if (arr[mid] === target) return mid;
    if (arr[mid] < target) left = mid + 1;
    else right = mid - 1;
  }
  return -1;
}

const nums = [1, 3, 5, 7, 9, 11, 15, 20];
console.log("Index of 7:", binarySearch(nums, 7)); // 3
console.log("Index of 4:", binarySearch(nums, 4)); // -1
'''
        elif language == "C++":
            code = '''#include <iostream>
#include <vector>

int binarySearch(const std::vector<int>& arr, int target) {
    int left = 0, right = static_cast<int>(arr.size()) - 1;
    while (left <= right) {
        int mid = left + (right - left) / 2;
        if (arr[mid] == target) return mid;
        if (arr[mid] < target) left = mid + 1;
        else right = mid - 1;
    }
    return -1;
}

int main() {
    std::vector<int> nums = {1, 3, 5, 7, 9, 11, 15, 20};
    std::cout << "Index of 7: " << binarySearch(nums, 7) << "\\n";
    std::cout << "Index of 4: " << binarySearch(nums, 4) << "\\n";
    return 0;
}
'''
        else: # Java
            code = '''public class BinarySearch {
    public static int search(int[] arr, int target) {
        int left = 0, right = arr.length - 1;
        while (left <= right) {
            int mid = left + (right - left) / 2;
            if (arr[mid] == target) return mid;
            if (arr[mid] < target) left = mid + 1;
            else right = mid - 1;
        }
        return -1;
    }

    public static void main(String[] args) {
        int[] nums = {1, 3, 5, 7, 9, 11, 15, 20};
        System.out.println("Index of 7: " + search(nums, 7));
        System.out.println("Index of 4: " + search(nums, 4));
    }
}
'''
        return {
            "mode": "DEMO MODE",
            "provider": "Local Template Synthesizer",
            "model": "Deterministic DSA Template",
            "language": language,
            "code": code,
            "explanation": "Generated standard O(log n) Binary Search algorithm preventing midpoint integer overflow.",
            "message": "Deterministic sample output. Configure an LLM API key in .env for custom requests."
        }

    # 4. LRU Cache
    if "lru" in p or "cache" in p:
        if language == "Python":
            code = '''from collections import OrderedDict
from typing import Any, Optional

class LRUCache:
    """
    Least Recently Used (LRU) Cache using OrderedDict.
    Get and Put operations run in O(1) average time.
    """
    def __init__(self, capacity: int):
        if capacity <= 0:
            raise ValueError("Capacity must be positive.")
        self.capacity = capacity
        self.cache = OrderedDict()

    def get(self, key: Any) -> Optional[Any]:
        if key not in self.cache:
            return None
        self.cache.move_to_end(key)
        return self.cache[key]

    def put(self, key: Any, value: Any) -> None:
        if key in self.cache:
            self.cache.move_to_end(key)
        self.cache[key] = value
        if len(self.cache) > self.capacity:
            self.cache.popitem(last=False)

if __name__ == "__main__":
    lru = LRUCache(2)
    lru.put(1, "A")
    lru.put(2, "B")
    print("Get 1:", lru.get(1))  # Returns 'A', marks 1 as recently used
    lru.put(3, "C")              # Evicts key 2
    print("Get 2:", lru.get(2))  # Returns None
    print("Get 3:", lru.get(3))  # Returns 'C'
'''
        elif language == "JavaScript":
            code = '''class LRUCache {
  constructor(capacity) {
    this.capacity = capacity;
    this.map = new Map();
  }

  get(key) {
    if (!this.map.has(key)) return null;
    const value = this.map.get(key);
    this.map.delete(key);
    this.map.set(key, value);
    return value;
  }

  put(key, value) {
    if (this.map.has(key)) this.map.delete(key);
    this.map.set(key, value);
    if (this.map.size > this.capacity) {
      const oldestKey = this.map.keys().next().value;
      this.map.delete(oldestKey);
    }
  }
}

const lru = new LRUCache(2);
lru.put(1, "A");
lru.put(2, "B");
console.log("Get 1:", lru.get(1));
lru.put(3, "C");
console.log("Get 2 (evicted):", lru.get(2));
console.log("Get 3:", lru.get(3));
'''
        elif language == "C++":
            code = '''#include <iostream>
#include <unordered_map>
#include <list>

class LRUCache {
    int capacity;
    std::list<std::pair<int, int>> items;
    std::unordered_map<int, std::list<std::pair<int, int>>::iterator> lookup;
public:
    LRUCache(int cap) : capacity(cap) {}

    int get(int key) {
        auto it = lookup.find(key);
        if (it == lookup.end()) return -1;
        items.splice(items.begin(), items, it->second);
        return it->second->second;
    }

    void put(int key, int value) {
        auto it = lookup.find(key);
        if (it != lookup.end()) {
            items.splice(items.begin(), items, it->second);
            it->second->second = value;
            return;
        }
        if (lookup.size() == capacity) {
            lookup.erase(items.back().first);
            items.pop_back();
        }
        items.emplace_front(key, value);
        lookup[key] = items.begin();
    }
};

int main() {
    LRUCache cache(2);
    cache.put(1, 10);
    cache.put(2, 20);
    std::cout << "Get 1: " << cache.get(1) << "\\n";
    cache.put(3, 30);
    std::cout << "Get 2 (evicted): " << cache.get(2) << "\\n";
    return 0;
}
'''
        else: # Java
            code = '''import java.util.LinkedHashMap;
import java.util.Map;

public class LRUCache<K, V> extends LinkedHashMap<K, V> {
    private final int capacity;

    public LRUCache(int capacity) {
        super(capacity, 0.75f, true);
        this.capacity = capacity;
    }

    @Override
    protected boolean removeEldestEntry(Map.Entry<K, V> eldest) {
        return size() > capacity;
    }

    public static void main(String[] args) {
        LRUCache<Integer, String> cache = new LRUCache<>(2);
        cache.put(1, "A");
        cache.put(2, "B");
        System.out.println("Get 1: " + cache.get(1));
        cache.put(3, "C");
        System.out.println("Get 2: " + cache.get(2)); // null
        System.out.println("Get 3: " + cache.get(3));
    }
}
'''
        return {
            "mode": "DEMO MODE",
            "provider": "Local Template Synthesizer",
            "model": "Deterministic DSA Template",
            "language": language,
            "code": code,
            "explanation": "Generated an O(1) LRU Cache data structure combining doubly-linked ordering with hash lookup.",
            "message": "Deterministic sample output. Configure an LLM API key in .env for custom requests."
        }

    # 5. REST API or Authentication
    if "api" in p or "auth" in p or "jwt" in p or "user" in p:
        if language == "Python":
            code = '''"""
Production-ready REST API starter with in-memory store and error handling.
Framework: FastAPI (synchronous & asynchronous endpoint design).
"""
from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, Field, EmailStr
from typing import List, Dict, Optional

app = FastAPI(title="User Management Microservice")

class UserCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    email: EmailStr
    role: str = Field(default="developer")

class UserResponse(BaseModel):
    id: int
    username: str
    email: str
    role: str

_db: Dict[int, Dict] = {}
_id_counter = 1

@app.post("/users", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def create_user(user: UserCreate):
    global _id_counter
    # Check uniqueness
    for existing in _db.values():
        if existing["email"] == user.email:
            raise HTTPException(status_code=400, detail="Email already registered")
    
    new_user = {"id": _id_counter, **user.model_dump()}
    _db[_id_counter] = new_user
    _id_counter += 1
    return new_user

@app.get("/users/{user_id}", response_model=UserResponse)
def get_user(user_id: int):
    if user_id not in _db:
        raise HTTPException(status_code=404, detail="User not found")
    return _db[user_id]
'''
        elif language == "JavaScript":
            code = '''/**
 * Express.js REST API with input validation and safe error handling.
 */
const express = require('express');
const app = express();
app.use(express.json());

const users = new Map();
let nextId = 1;

app.post('/api/users', (req, res) => {
  const { username, email } = req.body;
  if (!username || !email) {
    return res.status(400).json({ error: 'Username and email are required.' });
  }
  const id = nextId++;
  const user = { id, username, email, createdAt: new Date().toISOString() };
  users.set(id, user);
  res.status(201).json(user);
});

app.get('/api/users/:id', (req, res) => {
  const id = parseInt(req.params.id, 10);
  const user = users.get(id);
  if (!user) return res.status(404).json({ error: 'User not found' });
  res.json(user);
});

module.exports = app;
'''
        elif language == "C++":
            code = '''// Standard C++ Microservice / REST model with JSON serialization principles
#include <iostream>
#include <string>
#include <vector>
#include <memory>

struct User {
    int id;
    std::string username;
    std::string email;
};

class UserService {
    std::vector<User> users;
    int nextId = 1;
public:
    User createUser(const std::string& username, const std::string& email) {
        User u{nextId++, username, email};
        users.push_back(u);
        return u;
    }

    const User* findById(int id) const {
        for (const auto& u : users) {
            if (u.id == id) return &u;
        }
        return nullptr;
    }
};

int main() {
    UserService service;
    User u = service.createUser("student", "student@example.edu");
    std::cout << "Created user ID: " << u.id << ", Username: " << u.username << "\\n";
    return 0;
}
'''
        else: # Java
            code = '''// Spring Boot / Java REST Controller template
import java.util.*;

public class UserController {
    private final Map<Integer, User> userDatabase = new HashMap<>();
    private int idCounter = 1;

    public record User(int id, String username, String email) {}

    public synchronized User createUser(String username, String email) {
        if (username == null || email == null) {
            throw new IllegalArgumentException("Invalid user parameters");
        }
        User newUser = new User(idCounter++, username, email);
        userDatabase.put(newUser.id(), newUser);
        return newUser;
    }

    public static void main(String[] args) {
        UserController controller = new UserController();
        User user = controller.createUser("developer", "dev@campus.edu");
        System.out.println("Created User: " + user);
    }
}
'''
        return {
            "mode": "DEMO MODE",
            "provider": "Local Template Synthesizer",
            "model": "REST Architecture Template",
            "language": language,
            "code": code,
            "explanation": "Generated a structured REST endpoint pattern with data modeling, validation, and error handling.",
            "message": "Deterministic sample output. Configure an LLM API key in .env for custom requests."
        }

    # Generic Fallback Template based on prompt keywords
    clean_summary = re.sub(r'[^a-zA-Z0-9_ ]', '', prompt)[:60]
    if language == "Python":
        code = f'''"""
AI Software Engineering Copilot — Starter Template
Requirement: {prompt[:120]}
"""
from typing import Any, Dict, List, Optional

def solve_requirement(*args: Any, **kwargs: Any) -> Dict[str, Any]:
    """
    Core implementation function addressing:
    {prompt[:100]}
    
    Steps to complete:
    1. Parse and validate incoming inputs.
    2. Handle edge cases (empty collections, invalid boundaries).
    3. Execute the target business logic.
    4. Return clean, structured results.
    """
    # TODO: Implement domain logic
    result = {{
        "status": "success",
        "description": "{clean_summary}",
        "processed": True
    }}
    return result

if __name__ == "__main__":
    output = solve_requirement()
    print("Execution output:", output)
'''
    elif language == "JavaScript":
        code = f'''/**
 * AI Software Engineering Copilot — Starter Template
 * Requirement: {prompt[:120]}
 */

function solveRequirement(options = {{}}) {{
  // 1. Validate inputs
  if (typeof options !== 'object' || options === null) {{
    throw new TypeError('Options must be an object.');
  }}

  // 2. Core implementation
  const result = {{
    status: 'success',
    description: '{clean_summary}',
    timestamp: new Date().toISOString()
  }};

  return result;
}}

// Demonstration
console.log(solveRequirement());
'''
    elif language == "C++":
        code = f'''/**
 * AI Software Engineering Copilot — Starter Template
 * Requirement: {prompt[:120]}
 */
#include <iostream>
#include <string>

class Solution {{
public:
    bool execute() {{
        // Implementation for: {clean_summary}
        std::cout << "Executing logic for {clean_summary}..." << std::endl;
        return true;
    }}
}};

int main() {{
    Solution solution;
    solution.execute();
    return 0;
}}
'''
    else: # Java
        code = f'''/**
 * AI Software Engineering Copilot — Starter Template
 * Requirement: {prompt[:120]}
 */
public class Solution {{
    public static boolean execute() {{
        // Implementation for: {clean_summary}
        System.out.println("Executing logic for: {clean_summary}");
        return true;
    }}

    public static void main(String[] args) {{
        boolean success = execute();
        System.out.println("Completed with status: " + success);
    }}
}}
'''

    return {
        "mode": "DEMO MODE",
        "provider": "Local Heuristic Synthesizer",
        "model": "Generic Idiomatic Template",
        "language": language,
        "code": code,
        "explanation": f"Generated an idiomatic {language} scaffold tailored to '{prompt[:80]}...'.",
        "message": "Deterministic starter scaffold. Configure GEMINI_API_KEY in .env for dynamic AI generation."
    }
