from aiogram import Router

from bank import router as bank_router
from gold import router as gold_router
from mines import router as mines_router

router = Router()
router.include_router(bank_router)
router.include_router(gold_router)
router.include_router(mines_router)
