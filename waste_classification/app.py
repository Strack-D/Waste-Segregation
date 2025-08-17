import json
import re
from typing import List, Dict, Any
import requests
from bs4 import BeautifulSoup
import time
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np
import random

class AlgebraRAGSystem:
    """RAG-based algebra tutoring system using your converted dataset"""
    
    def __init__(self, dataset_file: str):
        print("🚀 Initializing Algebra RAG System...")
        self.problems = self.load_dataset(dataset_file)
        self.setup_retrieval_system()
        self.conversation_history = []
        print(f"✅ Loaded {len(self.problems)} problems")
    
    def load_dataset(self, dataset_file: str) -> List[Dict]:
        """Load the converted dataset"""
        try:
            with open(dataset_file, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            print(f"❌ Dataset file {dataset_file} not found!")
            return []
    
    def setup_retrieval_system(self):
        """Setup TF-IDF based retrieval"""
        if not self.problems:
            return
            
        # Create search corpus
        corpus = []
        for problem in self.problems:
            text = f"{problem['problem_statement']} {problem['topic']} {' '.join(problem.get('related_concepts', []))}"
            corpus.append(text)
        
        self.vectorizer = TfidfVectorizer(
            stop_words='english',
            ngram_range=(1, 2),  # Use both unigrams and bigrams
            max_features=5000
        )
        self.problem_vectors = self.vectorizer.fit_transform(corpus)
        print("🔍 Retrieval system ready")
    
    def find_relevant_problems(self, query: str, top_k: int = 3) -> List[Dict]:
        """Find most relevant problems for a query"""
        if not hasattr(self, 'vectorizer'):
            return self.problems[:top_k]  # Fallback
            
        query_vector = self.vectorizer.transform([query])
        similarities = cosine_similarity(query_vector, self.problem_vectors)[0]
        
        # Get top-k most similar
        top_indices = np.argsort(similarities)[-top_k:][::-1]
        relevant_problems = [self.problems[i] for i in top_indices]
        
        return relevant_problems
    
    def generate_response(self, user_query: str, response_type: str = "auto") -> str:
        """Generate a tutoring response"""
        
        # Find relevant problems
        relevant_problems = self.find_relevant_problems(user_query, top_k=2)
        
        if not relevant_problems:
            return "I don't have information about that topic yet. Can you ask about linear equations, quadratics, or polynomials?"
        
        best_match = relevant_problems[0]
        
        # Determine response type automatically if needed
        if response_type == "auto":
            response_type = self.classify_user_intent(user_query)
        
        # Generate appropriate response
        if response_type == "solve_problem":
            return self.generate_solution_response(best_match)
        elif response_type == "explain_concept":
            return self.generate_explanation_response(best_match)
        elif response_type == "get_hints":
            return self.generate_hint_response(best_match)
        else:
            return self.generate_general_response(best_match)
    
    def classify_user_intent(self, query: str) -> str:
        """Classify what the user wants"""
        query_lower = query.lower()
        
        if any(word in query_lower for word in ["solve", "find", "calculate", "what is"]):
            return "solve_problem"
        elif any(word in query_lower for word in ["explain", "how to", "why", "what does"]):
            return "explain_concept"
        elif any(word in query_lower for word in ["hint", "help", "stuck", "guide"]):
            return "get_hints"
        else:
            return "solve_problem"  # Default
    
    def generate_solution_response(self, problem: Dict) -> str:
        """Generate step-by-step solution"""
        response_parts = [
            f"🎯 **Problem**: {problem['problem_statement']}\n",
            "📝 **Solution**:\n"
        ]
        
        # Add each solution step
        for step in problem['solution_steps']:
            step_text = f"**Step {step['step']}**: {step['action']}"
            if step.get('equation'):
                step_text += f"\n   `{step['equation']}`"
            if step.get('explanation'):
                step_text += f"\n   💡 {step['explanation']}"
            response_parts.append(step_text + "\n")
        
        # Add final answer
        response_parts.append(f"✅ **Final Answer**: {problem['final_answer']}")
        
        # Add verification
        if problem.get('verification'):
            response_parts.append(f"🔍 **Verification**: {problem['verification']}")
        
        # Add common mistakes warning
        if problem.get('common_mistakes'):
            response_parts.append(f"\n⚠️ **Common Mistakes to Avoid**:")
            for mistake in problem['common_mistakes']:
                response_parts.append(f"   • {mistake}")
        
        return "\n".join(response_parts)
    
    def generate_explanation_response(self, problem: Dict) -> str:
        """Generate conceptual explanation"""
        response_parts = [
            f"📚 Let me explain the concept behind: {problem['problem_statement']}\n",
            f"🏷️ **Topic**: {problem['topic'].replace('_', ' ').title()}",
            f"📊 **Difficulty**: {problem['difficulty'].title()}\n"
        ]
        
        # Add conceptual explanation
        response_parts.append("🧠 **Key Concepts**:")
        for concept in problem.get('related_concepts', []):
            response_parts.append(f"   • {concept}")
        
        response_parts.append(f"\n📖 **Approach**: {problem.get('original_context', 'Step-by-step problem solving')}")
        
        # Add a worked example (using the current problem)
        response_parts.append(f"\n📝 **Example**: Let's work through this problem:")
        response_parts.append(f"   {problem['problem_statement']}")
        response_parts.append(f"   Answer: {problem['final_answer']}")
        
        return "\n".join(response_parts)
    
    def generate_hint_response(self, problem: Dict) -> str:
        """Generate helpful hints"""
        response_parts = [
            f"💡 **Hints for**: {problem['problem_statement']}\n"
        ]
        
        hints = problem.get('hints', [])
        if hints:
            for i, hint in enumerate(hints, 1):
                response_parts.append(f"**Hint {i}**: {hint}")
        else:
            # Generate generic hints
            response_parts.append("**Hint 1**: Break the problem down into smaller steps")
            response_parts.append("**Hint 2**: Identify what information you have and what you need to find")
            response_parts.append("**Hint 3**: Try substituting known values first")
        
        response_parts.append(f"\n🎯 **Problem Type**: {problem.get('problem_type', 'algebra_problem')}")
        
        return "\n".join(response_parts)
    
    def generate_general_response(self, problem: Dict) -> str:
        """Generate general helpful response"""
        return f"""
👋 I can help you with: **{problem['problem_statement']}**

Here are your options:
• Type "solve this" - I'll show you step-by-step solution
• Type "explain this" - I'll explain the concepts involved  
• Type "give me hints" - I'll provide helpful hints
• Type "show similar" - I'll show you similar problems

This is a **{problem['difficulty']}** level **{problem['topic'].replace('_', ' ')}** problem.
"""

# Example usage and testing
if __name__ == "__main__":
    print("🎓 Algebra Dataset Converter and RAG System")
    print("=" * 50)
    
    # Step 1: Convert your existing dataset
    converter = DatasetConverter()
    
    # Assuming your data is in 'original_dataset.json'
    # converter.convert_dataset('original_dataset.json', 'enhanced_dataset.json')
    
    # Step 2: Expand dataset with generated problems
    expander = DatasetExpansion()
    
    # Generate additional problems for each topic
    topics = ["linear_equations", "quadratic_equations", "polynomials"]
    all_generated = []
    
    for topic in topics:
        generated = expander.scrape_khan_academy_style_problems(topic, 20)
        all_generated.extend(generated)
        print(f"✅ Generated {len(generated)} problems for {topic}")
    
    # Convert generated problems too
    enhanced_generated = []
    for problem in all_generated:
        enhanced_problem = converter.convert_single_item(problem)
        enhanced_generated.append(enhanced_problem)
    
    # Save expanded dataset
    with open('expanded_dataset.json', 'w') as f:
        json.dump(enhanced_generated, f, indent=2)
    
    print(f"💾 Saved {len(enhanced_generated)} generated problems to expanded_dataset.json")
    
    # Step 3: Test the RAG system
    print("\n🧪 Testing RAG System...")
    
    # Create a small test dataset for demo
    test_problems = enhanced_generated[:10]
    with open('test_dataset.json', 'w') as f:
        json.dump(test_problems, f, indent=2)
    
    # Initialize RAG system
    rag_system = AlgebraRAGSystem('test_dataset.json')
    
    # Test different types of queries
    test_queries = [
        "How do I solve 3x + 7 = 22?",
        "Explain linear equations to me",
        "I'm stuck on this problem, can you give me hints?",
        "What's the equation of a line with slope 2 through point (1, 3)?"
    ]
    
    for query in test_queries:
        print(f"\n👤 User: {query}")
        response = rag_system.generate_response(query)
        print(f"🤖 Assistant: {response}")
        print("-" * 80)
