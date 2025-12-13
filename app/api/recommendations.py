from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from app.database import get_session
from app.models.user import RecommendationRequest, RecommendationResponse
from app.models.post import PostCreate, PostResponse
from app.models.reaction import ReactionCreate
from app.services.recommendation_service import recommendation_service

router = APIRouter(prefix="/recommendations", tags=["recommendations"])


@router.post("/", response_model=RecommendationResponse)
async def get_recommendations(
    request: RecommendationRequest,
    session: AsyncSession = Depends(get_session)
):
    """
    Get personalized post recommendations for a user
    
    Args:
        request: Recommendation request with user_id and parameters
        session: Database session
        
    Returns:
        List of recommended posts
    """
    try:
        logger.info(f"Getting recommendations for user {request.user_id}")
        response = await recommendation_service.get_recommendations(request, session)
        return response
    except Exception as e:
        logger.error(f"Error getting recommendations: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get recommendations: {str(e)}"
        )


@router.post("/posts", response_model=PostResponse, status_code=status.HTTP_201_CREATED)
async def create_post(
    post: PostCreate,
    session: AsyncSession = Depends(get_session)
):
    """
    Create a new post with text embedding
    
    Args:
        post: Post data
        session: Database session
        
    Returns:
        Created post
    """
    try:
        logger.info(f"Creating post {post.id}")
        response = await recommendation_service.create_post(post, session)
        return response
    except Exception as e:
        logger.error(f"Error creating post: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create post: {str(e)}"
        )


@router.post("/reactions", status_code=status.HTTP_201_CREATED)
async def create_reaction(
    reaction: ReactionCreate,
    session: AsyncSession = Depends(get_session)
):
    """
    Create a new reaction
    
    Args:
        reaction: Reaction data
        session: Database session
        
    Returns:
        Success message
    """
    try:
        logger.info(f"Creating reaction {reaction.id}")
        await recommendation_service.create_reaction(reaction, session)
        return {"message": "Reaction created successfully"}
    except Exception as e:
        logger.error(f"Error creating reaction: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create reaction: {str(e)}"
        )


@router.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "recommendation-service"
    }


@router.post("/refresh/{user_id}")
async def refresh_user_recommendations(
    user_id: str,
    session: AsyncSession = Depends(get_session)
):
    """
    Force refresh recommendations for a user
    
    Args:
        user_id: User ID
        session: Database session
        
    Returns:
        Success message
    """
    try:
        # Invalidate cache
        recommendation_service._invalidate_user_cache(user_id)
        
        # Recompute preferences
        from app.ml.recommender import recommender
        await recommender.get_user_preference_embedding(user_id, session)
        
        logger.info(f"Refreshed recommendations for user {user_id}")
        return {"message": f"Recommendations refreshed for user {user_id}"}
    except Exception as e:
        logger.error(f"Error refreshing recommendations: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to refresh recommendations: {str(e)}"
        )
