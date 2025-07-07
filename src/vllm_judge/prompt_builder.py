from typing import List, Dict, Union, Optional, Tuple, Any
import json

from vllm_judge.exceptions import InvalidInputError

class PromptBuilder:
    """Builds prompts for evaluation requests."""
    
    @staticmethod
    def build_messages(
        content: Union[str, Dict[str, str], List[Dict[str, str]]],
        criteria: str,
        input: Optional[str] = None,
        rubric: Union[str, Dict[Union[int, float], str]] = None,
        scale: Optional[Tuple[int, int]] = None,
        examples: List[Dict[str, Any]] = None,
        system_prompt: Optional[str] = None,
        context: Optional[str] = None,
        **kwargs
    ) -> List[Dict[str, str]]:
        """
        Build chat messages for evaluation.
        
        Args:
            content: Single response or dict with 'a' and 'b' for comparison, or list of dicts for conversation
            criteria: What to evaluate for
            input: Optional input/question/prompt that the response addresses
            rubric: Evaluation guide
            scale: Numeric scale (min, max)
            examples: Few-shot examples
            system_prompt: Custom system message
            context: Additional context
            **kwargs: Additional parameters
            
        Returns:
            List of chat messages
        """
        # Detect evaluation type
        is_comparison = isinstance(content, dict) and "a" in content and "b" in content
        if isinstance(content, list) and len(content) == 0:
                raise InvalidInputError("Conversation content cannot be an empty list.")
        is_conversation = isinstance(content, list) and all(
            isinstance(msg, dict) and "role" in msg and "content" in msg
            for msg in content
        )
        if isinstance(content, list) and not is_conversation:
            raise InvalidInputError(
                "Invalid content structure for conversation. Please provide a list of dicts with role and content fields."
            )
        output_format = """
# Output Format:

The JSON object MUST have exactly these three fields:

1. decision: (String | Boolean) This decision label should clearly state your main finding. This could be a string representing a specific class (eg., PASS, FAIL, CORRECT, INCORRECT, etc.) or a boolean value (true or false). If user provided a rubric, you should use the rubric to determine the decision label.
2. score: (Number | null) A numerical score for the evaluation. If scoring is requested, provide the score as a number. If scoring is NOT requested or is not applicable for the specific task, you MUST use the value null for this field.
3. reasoning: (String) A concise explanation justifying your decision and score (if a score was provided). This reasoning must directly and logically support your evaluation and refer to the specific evaluation criteria.

The JSON object MUST be well-formed and adhere strictly to the following structure:

{
    "decision": <your judgment - string|boolean>,
    "reasoning": <concise explanation of your judgment - string>,
    "score": <numeric score if requested, otherwise null - number|null>
}
        """
        
        # System message
        if not system_prompt:
            system_prompt = """You are an impartial judge and expert evaluator. Your task is to evaluate the provided content based on the specific evaluation criteria and rubric.
# Key Instructions:
1. Your evaluation must be objective, consistent, and based solely on the specified criteria. Do not let your own opinions or biases interfere.
2. Focus exclusively on quality assessment. 
3. Do not be influenced by the length of the responses unless response length is explicitly relevant to the specified evaluation criteria (e.g., a task assessing conciseness or verbosity).
4. Your entire response MUST be a single, valid JSON object and nothing else. Do not include any text or conversational filler before or after this JSON object.

"""
        system_prompt += output_format
        
        # Build user message
        user_content = PromptBuilder._build_user_prompt(
            content=content,
            input=input,
            criteria=criteria,
            rubric=rubric,
            scale=scale,
            examples=examples,
            is_comparison=is_comparison,
            is_conversation=is_conversation,
            context=context,
            **kwargs
        )
        
        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content}
        ]
    
    @staticmethod
    def _build_user_prompt(
        content: Union[str, Dict[str, str], List[Dict[str, str]]],
        criteria: str,
        rubric: Union[str, Dict[Union[int, float], str]],
        scale: Optional[Tuple[int, int]],
        examples: List[Dict[str, Any]],
        is_comparison: bool,
        is_conversation: bool,
        context: Optional[str] = None,
        input: Optional[str] = None,
        **kwargs
    ) -> str:
        """Build the user message content."""
        parts = []

        # Add input section if provided
        if input:
            parts.append("Given the following input/question:")
            parts.append(f'"{input}"')
            parts.append("")
        
        parts.append("## Content to evaluate:")
        if is_comparison:
            parts.append(f"**Response A:**\n{content['a']}")
            parts.append(f"**Response B:**\n{content['b']}")
        elif is_conversation:
            parts.append("**Conversation Start:**")
            for i, msg in enumerate(content):
                role = msg["role"].title() 
                parts.append(f"{role}: {msg['content']}")
                if i < len(content) - 1:  # Add spacing except for last message
                    parts.append("")
            parts.append("**Conversation End:**")
        else:
            parts.append(content)
        
        parts.append("## Evaluation Criteria:")
        
        # Task description
        if is_comparison:
            parts.append(f"Compare the two responses based on: {criteria}")
            if context:
                parts.append(f"\nContext: {context}")
        elif is_conversation:
            parts.append(f"Evaluate the conversation based on: {criteria}")
            parts.append("Consider the full context, flow, and interaction quality.")
            if context:
                parts.append(f"\nContext: {context}")
        else:
            parts.append(f"Evaluate the content based on: {criteria}")
            if context:
                parts.append(f"\nContext: {context}")
        
        parts.append(f"\nYou must return a decision label/class (your main judgement) for the `decision` field and a concise explanation for the `reasoning` field in the JSON object.")

        # Add scale and rubric
        if scale:
            parts.append(f"In addition to these, provide a score from {scale[0]} to {scale[1]}")
            
            if isinstance(rubric, dict):
                parts.append("\nScoring guide:")
                # Sort by score in descending order
                sorted_items = sorted(rubric.items(), key=lambda x: float(x[0]), reverse=True)
                for score, description in sorted_items:
                    parts.append(f"- {score}: {description}")
            elif rubric:
                parts.append(f"\nEvaluation guide: {rubric}")
        elif rubric:
            parts.append("\nIn addition to these, provide a score if required by the following evaluation guide.")
            parts.append(f"\nEvaluation guide: {rubric}")
        
        # Add examples if provided
        if examples:
            parts.append("\nExample evaluations:")
            for i, ex in enumerate(examples):
                parts.append(f"Example {i+1}:")
                parts.append("Request:")
                # Handle different example formats
                if "input" in ex:
                    parts.append(f"Input: {ex['input']}")
                if "content" in ex:
                    if isinstance(ex["content"], list):
                        parts.append("**Conversation Start:**")
                        for msg in ex["content"]:
                            role = msg["role"].title()
                            parts.append(f"{role}: {msg['content']}")
                        parts.append("**Conversation End:**")
                    else:
                        parts.append(f"Content: {ex['content']}")
                elif "text" in ex:
                    parts.append(f"Text: {ex['text']}")
                
                parts.append("Response:")
                
                response = {}
                if "decision" not in ex or ex["decision"] is None or ex["decision"] == "":
                    raise ValueError("Example must include a decision field")
                
                response["decision"] = ex["decision"]
                if "score" in ex:
                    response["score"] = ex["score"]
                
                if "reasoning" in ex:
                    response["reasoning"] = ex["reasoning"]
                
                parts.append(json.dumps(response))
        
        # Add any additional instructions
        if kwargs.get("additional_instructions"):
            parts.append(f"Additional instructions: {kwargs['additional_instructions']}")

        # Output format instructions
        parts.append("\nYou must respond in JSON format:")
        parts.append("""{
    "decision": <your judgment - string|boolean>,
    "reasoning": "<concise explanation of your judgment>",
    "score": <numeric score if requested, otherwise null>
}""")
        
        return "\n".join(parts)
    
    @staticmethod
    def format_messages_as_text(messages: List[Dict[str, str]]) -> str:
        """
        Format chat messages as plain text for completion API.
        
        Args:
            messages: List of chat messages
            
        Returns:
            Formatted text prompt
        """
        parts = []
        
        for message in messages:
            role = message["role"]
            content = message["content"]
            
            if role == "system":
                parts.append(f"System: {content}")
            elif role == "user":
                parts.append(f"\nUser: {content}")
            elif role == "assistant":
                parts.append(f"\nAssistant: {content}")
        
        # Add a prompt for the assistant to respond
        parts.append("\nAssistant:")
        
        return "\n".join(parts)