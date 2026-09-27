import random
from datetime import datetime

from sqlalchemy.orm import Session

from app.models import (
    Exam, ExamAttempt, ExamAnswer, Question, GradeRecord, QuestionStatistics, Certificate,
)


def calculate_exam_stats(db: Session, exam_id: int) -> dict:
    """考试整体统计：平均分、最高/最低分、及格率、分数分布、预约与补考情况"""
    exam = db.query(Exam).filter(Exam.id == exam_id).first()
    if not exam:
        raise ValueError("考试不存在")

    from app.models import ExamBooking
    from app.services import booking_service
    booking_service.sync_missed(db, exam_id=exam_id)

    graded = (
        db.query(ExamAttempt)
        .filter(ExamAttempt.exam_id == exam_id, ExamAttempt.status == "graded")
        .all()
    )

    # 预约维度（与 booking_service 保持一致的口径）
    valid_bookings = (
        db.query(ExamBooking)
        .filter(
            ExamBooking.exam_id == exam_id,
            ExamBooking.status.in_(("approved", "used", "missed")),
        )
        .count()
    )
    absent_count = (
        db.query(ExamBooking)
        .filter(ExamBooking.exam_id == exam_id, ExamBooking.status == "missed")
        .count()
    )

    if not graded:
        return {
            "exam_id": exam_id, "attempt_count": 0,
            "avg_score": 0, "max_score": 0, "min_score": 0,
            "pass_rate": 0, "distribution": {},
            "student_count": 0, "pass_count": 0,
            "first_attempt_count": 0, "retake_attempt_count": 0,
            "retake_pass_count": 0, "retake_pass_rate": 0.0,
            "booked_count": valid_bookings, "attended_count": 0,
            "attendance_rate": 0.0, "absent_count": absent_count,
        }

    scores = [a.score for a in graded]
    passed_attempts = [a for a in graded if a.is_passed == 1]
    passed_users = {a.user_id for a in passed_attempts}
    retake_attempts = [a for a in graded if a.attempt_no > 1]
    retake_pass = [a for a in retake_attempts if a.is_passed == 1]
    attended_users = {a.user_id for a in graded}
    attendance_rate = round(len(attended_users) / valid_bookings * 100, 1) if valid_bookings else 0.0
    distribution = {
        "0-59": len([s for s in scores if s < 60]),
        "60-69": len([s for s in scores if 60 <= s < 70]),
        "70-79": len([s for s in scores if 70 <= s < 80]),
        "80-89": len([s for s in scores if 80 <= s < 90]),
        "90-100": len([s for s in scores if s >= 90]),
    }
    return {
        "exam_id": exam_id,
        "attempt_count": len(scores),
        "avg_score": round(sum(scores) / len(scores), 1),
        "max_score": max(scores),
        "min_score": min(scores),
        "pass_rate": round(len(passed_attempts) / len(scores) * 100, 1),
        "distribution": distribution,
        # 人数维度（支持补考：一人多次只计 1 人）
        "student_count": len(attended_users),
        "pass_count": len(passed_users),
        # 补考维度
        "first_attempt_count": len([a for a in graded if a.attempt_no == 1]),
        "retake_attempt_count": len(retake_attempts),
        "retake_pass_count": len(retake_pass),
        "retake_pass_rate": round(len(retake_pass) / len(retake_attempts) * 100, 1) if retake_attempts else 0.0,
        # 预约与到考
        "booked_count": valid_bookings,
        "attended_count": len(attended_users),
        "attendance_rate": attendance_rate,
        "absent_count": absent_count,
    }


def calculate_question_stats(db: Session, question_id: int) -> QuestionStatistics:
    """单题统计：正确率、实际难度(1-正确率)、区分度(高分组-低分组正确率)"""
    answers = (
        db.query(ExamAnswer)
        .filter(ExamAnswer.question_id == question_id)
        .all()
    )
    if not answers:
        return QuestionStatistics(question_id=question_id)

    total = len(answers)
    correct = sum(1 for a in answers if a.is_correct == 1)

    # 区分度：取全部成绩中的高分组(前27%)与低分组(后27%)比较该题正确率
    attempt_ids = {a.attempt_id for a in answers}
    attempts = (
        db.query(ExamAttempt)
        .filter(ExamAttempt.id.in_(attempt_ids), ExamAttempt.status == "graded")
        .order_by(ExamAttempt.score.desc())
        .all()
    )
    n = len(attempts)
    high_n = max(1, int(n * 0.27))
    high_ids = {a.id for a in attempts[:high_n]}
    low_ids = {a.id for a in attempts[-high_n:]}

    high_correct = sum(1 for a in answers if a.attempt_id in high_ids and a.is_correct == 1)
    low_correct = sum(1 for a in answers if a.attempt_id in low_ids and a.is_correct == 1)
    discrimination = high_correct / high_n - low_correct / high_n

    stats = QuestionStatistics(
        question_id=question_id,
        total_attempts=total,
        correct_count=correct,
        wrong_count=total - correct,
        average_score=round(sum(a.score for a in answers) / total, 2),
        difficulty_actual=round(1 - correct / total, 2),
        discrimination_actual=round(discrimination, 2),
    )
    existing = (
        db.query(QuestionStatistics)
        .filter(QuestionStatistics.question_id == question_id)
        .first()
    )
    if existing:
        existing.total_attempts = stats.total_attempts
        existing.correct_count = stats.correct_count
        existing.wrong_count = stats.wrong_count
        existing.average_score = stats.average_score
        existing.difficulty_actual = stats.difficulty_actual
        existing.discrimination_actual = stats.discrimination_actual
        stats = existing
    else:
        db.add(stats)
    db.commit()
    db.refresh(stats)
    return stats


def _best_attempts(db: Session, exam_id: int) -> list[ExamAttempt]:
    """每个学生在该考试中的最佳（最高分）已交卷记录。"""
    graded = (
        db.query(ExamAttempt)
        .filter(ExamAttempt.exam_id == exam_id, ExamAttempt.status == "graded")
        .order_by(ExamAttempt.score.desc())
        .all()
    )
    best: dict[int, ExamAttempt] = {}
    for a in graded:
        if a.user_id not in best or a.score > best[a.user_id].score:
            best[a.user_id] = a
    return list(best.values())


def get_user_rank(db: Session, user_id: int, exam_id: int,
                  attempt_id: int | None = None) -> dict:
    """
    获取用户在某次考试中的名次与百分位（按每个学生的最佳成绩排名）。
    名次规则：分数高于该用户最佳成绩的人数 + 1（同分同名次）。
    可传 attempt_id 定位某次具体补考，用于交卷后立即结算；
    GradeRecord 与 attempt 一一对应（upsert）。
    """
    if attempt_id is not None:
        target = (
            db.query(ExamAttempt)
            .filter(
                ExamAttempt.id == attempt_id,
                ExamAttempt.user_id == user_id,
                ExamAttempt.status == "graded",
            )
            .first()
        )
    else:
        target = (
            db.query(ExamAttempt)
            .filter(
                ExamAttempt.exam_id == exam_id,
                ExamAttempt.user_id == user_id,
                ExamAttempt.status == "graded",
            )
            .order_by(ExamAttempt.score.desc())
            .first()
        )
    if not target:
        raise ValueError("尚未完成该考试")

    best = _best_attempts(db, exam_id)
    best_by_user = {a.user_id: a for a in best}
    user_best = best_by_user.get(user_id, target)
    total = len(best)
    higher = sum(1 for a in best if a.score > user_best.score)

    rank = higher + 1
    percentile = round(100 * (1 - higher / total), 1) if total else 0.0

    record = (
        db.query(GradeRecord)
        .filter(GradeRecord.attempt_id == target.id)
        .first()
    )
    if not record:
        record = GradeRecord(
            attempt_id=target.id,
            user_id=user_id,
            exam_id=exam_id,
        )
        db.add(record)
    record.score = target.score
    record.rank = rank
    record.percentile = percentile
    db.commit()
    return {"user_id": user_id, "exam_id": exam_id, "score": target.score,
            "rank": rank, "total": total, "percentile": percentile}


def get_leaderboard(db: Session, exam_id: int, limit: int = 20) -> list[dict]:
    """排行榜：每个学生取最佳成绩，同分同名次。"""
    best = _best_attempts(db, exam_id)
    best.sort(key=lambda a: (-a.score, a.submit_time or datetime.max))
    best = best[:limit]
    result = []
    prev_score = None
    prev_rank = 0
    for i, a in enumerate(best, start=1):
        if a.score != prev_score:
            rank = i
            prev_rank = i
            prev_score = a.score
        else:
            rank = prev_rank
        result.append({
            "user_id": a.user_id,
            "username": a.user.username,
            "real_name": a.user.real_name,
            "score": a.score,
            "rank": rank,
            "submit_time": a.submit_time,
        })
    return result


def generate_certificate(db: Session, user_id: int, exam_id: int) -> Certificate:
    """通过考试后生成证书，编号唯一。补考通过取最高成绩。"""
    attempt = (
        db.query(ExamAttempt)
        .filter(
            ExamAttempt.exam_id == exam_id,
            ExamAttempt.user_id == user_id,
            ExamAttempt.status == "graded",
            ExamAttempt.is_passed == 1,
        )
        .order_by(ExamAttempt.score.desc())
        .first()
    )
    if not attempt:
        raise ValueError("未通过考试，无法生成证书")

    existing = (
        db.query(Certificate)
        .filter(Certificate.user_id == user_id, Certificate.exam_id == exam_id)
        .first()
    )
    if existing:
        # 补考取得更高分时更新证书成绩
        if existing.score < attempt.score:
            existing.score = attempt.score
            db.commit()
            db.refresh(existing)
        return existing

    cert_no = f"CERT-{exam_id}-{user_id}-{random.randint(1000, 9999)}"
    cert = Certificate(
        user_id=user_id,
        exam_id=exam_id,
        certificate_no=cert_no,
        score=attempt.score,
    )
    db.add(cert)
    db.commit()
    db.refresh(cert)
    return cert


def auto_issue_certificate(db: Session, attempt: ExamAttempt) -> Certificate | None:
    """交卷评分后联动发证：通过且此前无有效证书时自动发放。"""
    if attempt.is_passed != 1 or attempt.status != "graded":
        return None
    existing = (
        db.query(Certificate)
        .filter(
            Certificate.user_id == attempt.user_id,
            Certificate.exam_id == attempt.exam_id,
            Certificate.is_valid == 1,
        )
        .first()
    )
    if existing:
        if existing.score < attempt.score:
            existing.score = attempt.score
            db.commit()
        return None
    return generate_certificate(db, attempt.user_id, attempt.exam_id)


def list_certificates(db: Session, user_id: int):
    return db.query(Certificate).filter(Certificate.user_id == user_id).all()
