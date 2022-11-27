from typing import List, Dict, Optional

from fastapi import Depends, HTTPException, APIRouter, status
from fastapi.security import OAuth2PasswordRequestForm

from ..auth import (
    CredentialsProvider,
    TokenGen
)
from ..auth import (
    TokenProvider
)
from ..celery_app.tasks import task_registry, TaskChainer
from ..models.auth import Token
from ..models.ml import Trainer, Dataset
from ..models.users import User

router = APIRouter()


@router.post("/users/me/", response_model=User)
async def read_users_me(
        current_user: User = Depends(TokenProvider().load_user)
):
    return current_user


@router.post("/train/")
async def train(
        trainer: Trainer,
        dataset: Dataset,
        partitions: Optional[List[Dict]] = None,
        current_user: User = Depends(TokenProvider().load_user)
):
    """Creates forecaster.

    By "forecaster" it is meant any time series estimator.
    """
    load_dataset_kwargs = {
        'dataset': dataset.dict(),
        'user': current_user.dict(),
        'partitions': partitions,
        'format': 'pandas',
        'return_schema': True,
        'enforce_schema_dtypes': True
    }

    # Get tasks.
    load_dataset_task = task_registry.get_task('LoadDatasetTask')
    train_task = task_registry.get_task('TrainTask')

    # Make chain.
    chainer = TaskChainer()
    chainer.add_task(load_dataset_task, **load_dataset_kwargs)
    chainer.add_task(train_task, trainer=trainer.dict())
    chain = chainer.make_chain()

    async_task = chain()
    return {'async_task_id': async_task.id}


@router.post("/login", response_model=Token)
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    user = CredentialsProvider().authenticate(form_data)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token = TokenGen().generate_token(data={"sub": user.username})
    return {"access_token": access_token, "token_type": "bearer"}
