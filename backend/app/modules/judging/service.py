from uuid import UUID


class JudgingService:
    # shortcut: chưa có phân công Phase 4; mặc định đóng quyền, nối DB cùng khóa event ở Phase 4.
    async def can_read_submission(self, user_id: UUID, team_id: UUID, round_id: UUID) -> bool:
        return False

    async def submissions_frozen(self, round_id: UUID) -> bool:
        return False
