"""Deleting a company or a whiteboard with everything that hangs off it.

SQLite does not enforce foreign keys by default, so a missing cascade only leaves orphaned rows
there; PostgreSQL rejects the delete. Run with TEST_DATABASE_URL to check both.
"""

from datetime import date, datetime


def _rich_company(seeded):
    """A company with one of every related record, plus records outside it that point into it."""
    from models import (Audit, ClientCredential, ClientFile, Company, Competitor, ContentPost, Contract,
                        EmailLog, Expense, GscSnapshot, Mention, Note, Offer, Package, Payment, Project, Task,
                        TaskComment, User, Visit, Whiteboard, WhiteboardStroke, db)

    with seeded.app_context():
        anna = User.query.filter_by(email="anna@example.com").one()
        c = Company(name="Firma do usunięcia")
        db.session.add(c)
        db.session.flush()
        project = Project(company_id=c.id, name="Projekt do usunięcia")
        db.session.add(project)
        db.session.flush()
        post = ContentPost(company_id=c.id, title="Wpis do usunięcia")
        db.session.add(post)
        db.session.flush()
        project_task = Task(title="Zadanie w projekcie", company_id=c.id, project_id=project.id,
                            content_post_id=post.id)
        loose_task = Task(title="Zadanie przypięte do firmy", company_id=c.id)
        db.session.add_all([project_task, loose_task])
        db.session.flush()
        subtask = Task(title="Podzadanie", parent_task_id=project_task.id, project_id=project.id)
        db.session.add(subtask)
        db.session.flush()
        comment = TaskComment(task_id=project_task.id, user_id=anna.id, body="@Anna zerknij")
        db.session.add(comment)
        db.session.flush()
        db.session.add(Mention(mentioned_user_id=anna.id, author_user_id=anna.id, source_type="task_comment",
                               source_id=comment.id, task_id=project_task.id))
        pdf = ClientFile(company_id=c.id, project_id=project.id, task_id=project_task.id,
                         filename="umowa.pdf", stored_path="uploads/none/umowa.pdf")
        db.session.add(pdf)
        db.session.flush()
        db.session.add(ClientFile(company_id=c.id, filename="umowa-v2.pdf", stored_path="uploads/none/umowa-v2.pdf",
                                  version=2, parent_file_id=pdf.id))
        db.session.add(Contract(company_id=c.id, name="Umowa", generated_pdf_file_id=pdf.id))
        expense = Expense(title="Koszt na klienta", client_id=c.id, amount_net=100, attachment_file_id=pdf.id)
        db.session.add(expense)
        db.session.flush()
        post.writer_cost_expense_id = expense.id
        audit = Audit(company_id=c.id)
        db.session.add(audit)
        db.session.flush()
        db.session.add(Competitor(audit_id=audit.id, name="Konkurent"))
        db.session.add(Offer(company_id=c.id, package_id=Package.query.first().id, audit_id=audit.id))
        db.session.add_all([
            Note(company_id=c.id, project_id=project.id, content="Notatka", scope="company"),
            Payment(company_id=c.id, title="Abonament", amount_net=1000),
            Visit(company_id=c.id, scheduled_at=datetime(2026, 5, 4, 10, 0)),
            ClientCredential(company_id=c.id, label="WordPress"),
            GscSnapshot(company_id=c.id, date_range_start=date(2026, 4, 1), date_range_end=date(2026, 4, 30)),
            EmailLog(company_id=c.id, to_address="kontakt@example.com", subject_rendered="Oferta"),
        ])
        board = Whiteboard(name="Tablica firmy", company_id=c.id)
        db.session.add(board)
        db.session.flush()
        db.session.add(WhiteboardStroke(whiteboard_id=board.id, tool="pen", points=[[0, 0], [5, 5]]))
        db.session.commit()
        return {"company": c.id, "loose_task": loose_task.id, "expense": expense.id, "board": board.id,
                "project_task": project_task.id, "subtask": subtask.id}


def test_company_delete_removes_its_data_and_detaches_the_rest(client, seeded):
    from models import (Audit, ClientFile, Company, ContentPost, EmailLog, Expense, Mention, Project, Task,
                        Whiteboard, db)

    ids = _rich_company(seeded)
    r = client.post(f"/companies/{ids['company']}/delete")
    assert r.status_code == 302
    with seeded.app_context():
        assert db.session.get(Company, ids["company"]) is None
        assert Project.query.filter_by(company_id=ids["company"]).count() == 0
        assert Audit.query.filter_by(company_id=ids["company"]).count() == 0
        assert ClientFile.query.filter_by(company_id=ids["company"]).count() == 0
        assert ContentPost.query.filter_by(company_id=ids["company"]).count() == 0
        assert db.session.get(Task, ids["project_task"]) is None and db.session.get(Task, ids["subtask"]) is None
        assert Mention.query.filter_by(task_id=ids["project_task"]).count() == 0
        # Records that live on their own stay, without the company (costs, history, boards, loose tasks)
        loose = db.session.get(Task, ids["loose_task"])
        assert loose is not None and loose.company_id is None
        expense = db.session.get(Expense, ids["expense"])
        assert expense is not None and expense.client_id is None and expense.attachment_file_id is None
        assert db.session.get(Whiteboard, ids["board"]).company_id is None
        assert EmailLog.query.filter_by(to_address="kontakt@example.com", company_id=None).count() == 1
        db.session.delete(loose)
        db.session.delete(expense)
        db.session.commit()


def test_whiteboard_delete_includes_erased_elements(client, seeded):
    from models import Whiteboard, WhiteboardDeletion, WhiteboardStroke, db

    with seeded.app_context():
        board = Whiteboard(name="Tablica z wymazanymi")
        db.session.add(board)
        db.session.flush()
        db.session.add_all([
            WhiteboardStroke(whiteboard_id=board.id, tool="pen", points=[[0, 0], [1, 1]]),
            WhiteboardStroke(whiteboard_id=board.id, tool="pen", points=[[2, 2], [3, 3]], deleted=True),
            WhiteboardDeletion(whiteboard_id=board.id, stroke_id=0),
        ])
        db.session.commit()
        board_id = board.id
    assert client.post(f"/tablica/{board_id}/delete").status_code == 302
    with seeded.app_context():
        assert db.session.get(Whiteboard, board_id) is None
        assert WhiteboardStroke.query.filter_by(whiteboard_id=board_id).count() == 0
