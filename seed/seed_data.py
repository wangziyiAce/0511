"""种子数据脚本 - 课程与活动数据"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + "/..")

from utils.database import SessionLocal
from models.chat import CourseProject, EventLecture
from datetime import datetime


def seed_courses():
    """插入课程种子数据"""
    courses = [
        CourseProject(
            project_name="雅思7分冲刺班",
            category="语言培训",
            description="针对雅思目标7分的学员，涵盖听说读写四项技能强化训练，包含10次全真模考与名师讲评。",
            target_audience="雅思基础5.5分以上",
            price=8800.00,
            duration="8周",
            tags=["名师授课", "小班教学", "模考+讲评"],
            status=1,
        ),
        CourseProject(
            project_name="托福100分突破班",
            category="语言培训",
            description="系统性托福备考课程，重点突破阅读与听力高分瓶颈，配备独家真题题库。",
            target_audience="托福基础70分以上",
            price=9800.00,
            duration="10周",
            tags=["真题题库", "一对一辅导", "考前冲刺"],
            status=1,
        ),
        CourseProject(
            project_name="日语N2速成班",
            category="语言培训",
            description="从零基础到N2，采用沉浸式教学法，6个月快速达标。",
            target_audience="零基础或N5水平",
            price=6800.00,
            duration="24周",
            tags=["沉浸式教学", "日本外教", "考级保过"],
            status=1,
        ),
        CourseProject(
            project_name="科研背景提升项目",
            category="背景提升",
            description="与985高校教授合作，参与真实科研课题，产出论文或专利，助力留学申请。",
            target_audience="本科在读学生",
            price=29800.00,
            duration="12周",
            tags=["名校教授", "科研论文", "推荐信"],
            status=1,
        ),
        CourseProject(
            project_name="名企实习内推计划",
            category="背景提升",
            description="对接世界500强企业，提供远程/实地实习机会，涵盖金融、咨询、互联网等行业。",
            target_audience="大三及以上学生",
            price=15800.00,
            duration="8-12周",
            tags=["500强企业", "实习证明", "职业规划"],
            status=1,
        ),
        CourseProject(
            project_name="英国硕士直通车",
            category="留学申请",
            description="一站式英国TOP30硕士申请服务，包含选校定位、文书润色、面试辅导、签证指导。",
            target_audience="本科毕业生或大四在读",
            price=39800.00,
            duration="6-12个月",
            tags=["TOP30保录", "文书定制", "面试辅导"],
            status=1,
        ),
        CourseProject(
            project_name="美国名校申请套餐",
            category="留学申请",
            description="针对美国TOP50院校的全套申请服务，包含背景提升规划、选校策略、文书创作、面试培训。",
            target_audience="GPA 3.0以上",
            price=59800.00,
            duration="12-18个月",
            tags=["TOP50名校", "全流程服务", "奖学金申请"],
            status=1,
        ),
        CourseProject(
            project_name="澳大利亚移民+留学双规划",
            category="留学申请",
            description="结合澳洲移民政策，提供留学+移民双路径规划，涵盖职业评估、院校申请、签证办理。",
            target_audience="有意向移民澳洲的学生",
            price=35800.00,
            duration="8-14个月",
            tags=["移民规划", "职业评估", "双路径"],
            status=1,
        ),
        CourseProject(
            project_name="GRE/GMAT联报班",
            category="语言培训",
            description="GRE与GMAT联合备考课程，适合尚未确定目标国家的学生，双线准备。",
            target_audience="大三及以上学生",
            price=12800.00,
            duration="16周",
            tags=["双线备考", "自适应模考", "高分保障"],
            status=1,
        ),
        CourseProject(
            project_name="艺术作品集辅导",
            category="背景提升",
            description="针对申请海外艺术院校的学生，提供一对一作品集指导与创作支持。",
            target_audience="艺术/设计专业学生",
            price=25800.00,
            duration="16周",
            tags=["一对一辅导", "作品集制作", "名校导师"],
            status=1,
        ),
    ]

    db = SessionLocal()
    try:
        # 检查是否已有数据
        existing = db.query(CourseProject).count()
        if existing > 0:
            print(f"课程数据已存在 ({existing} 条)，跳过种子数据插入")
            return

        db.add_all(courses)
        db.commit()
        print(f"课程种子数据插入成功: {len(courses)} 条")
    except Exception as e:
        db.rollback()
        print(f"课程种子数据插入失败: {e}")
        raise
    finally:
        db.close()


def seed_events():
    """插入活动种子数据"""
    events = [
        EventLecture(
            event_name="英国留学申请攻略讲座",
            event_type="online",
            description="详解2026年英国硕士申请流程、选校策略与材料准备要点，由资深留学顾问主讲。",
            start_time=datetime(2026, 7, 15, 14, 0, 0),
            end_time=datetime(2026, 7, 15, 16, 0, 0),
            location="线上 - 腾讯会议（会议号：123-456-789）",
            max_participants=100,
            current_participants=0,
            status="upcoming",
        ),
        EventLecture(
            event_name="美国TOP30名校申请经验分享",
            event_type="offline",
            description="邀请已获得哈佛、斯坦福等名校offer的学长学姐现场分享申请经验与心得。",
            start_time=datetime(2026, 7, 20, 10, 0, 0),
            end_time=datetime(2026, 7, 20, 12, 0, 0),
            location="北京市朝阳区建国路88号 SOHO现代城A座15层",
            max_participants=50,
            current_participants=0,
            status="upcoming",
        ),
        EventLecture(
            event_name="雅思口语高分技巧公开课",
            event_type="online",
            description="雅思考官亲授口语高分技巧，涵盖Part1-3答题策略与常见误区解析。",
            start_time=datetime(2026, 7, 18, 19, 0, 0),
            end_time=datetime(2026, 7, 18, 20, 30, 0),
            location="线上 - Zoom（会议号：987-654-321）",
            max_participants=200,
            current_participants=0,
            status="upcoming",
        ),
        EventLecture(
            event_name="留学文书写作工作坊",
            event_type="hybrid",
            description="由前招生官亲授留学文书写作技巧，现场点评修改真实文书案例。",
            start_time=datetime(2026, 7, 25, 14, 0, 0),
            end_time=datetime(2026, 7, 25, 17, 0, 0),
            location="上海市静安区南京西路1515号 + 线上同步直播",
            max_participants=30,
            current_participants=0,
            status="upcoming",
        ),
        EventLecture(
            event_name="留学生海外生活指南分享会",
            event_type="online",
            description="邀请海外在读学长学姐分享海外生活经验，涵盖住宿、医疗、社交等实用话题。",
            start_time=datetime(2026, 8, 1, 15, 0, 0),
            end_time=datetime(2026, 8, 1, 16, 30, 0),
            location="线上 - 腾讯会议",
            max_participants=150,
            current_participants=0,
            status="upcoming",
        ),
    ]

    db = SessionLocal()
    try:
        existing = db.query(EventLecture).count()
        if existing > 0:
            print(f"活动数据已存在 ({existing} 条)，跳过种子数据插入")
            return

        db.add_all(events)
        db.commit()
        print(f"活动种子数据插入成功: {len(events)} 条")
    except Exception as e:
        db.rollback()
        print(f"活动种子数据插入失败: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed_courses()
    seed_events()
    print("种子数据插入完成！")
