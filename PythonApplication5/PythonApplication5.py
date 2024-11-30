import sys
import json
import uuid
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QVBoxLayout, QHBoxLayout,
    QWidget, QLineEdit, QPushButton, QTableWidget,
    QTableWidgetItem, QMessageBox, QAbstractItemView
)
from PyQt5.QtCore import Qt
from datetime import datetime, timedelta
from simpleai.search import SearchProblem, greedy

# Hàm tiện ích
def parse_time(time_str):
    """Chuyển đổi chuỗi giờ (HH:MM) thành datetime."""
    return datetime.strptime(time_str, "%H:%M")

def add_days(start_time, days):
    """Thêm số ngày vào một datetime."""
    return start_time + timedelta(days=days)

def save_tasks_to_file(tasks, filename="tasks.json"):
    """Lưu danh sách công việc vào file JSON."""
    with open(filename, "w") as file:
        json.dump(tasks, file, indent=4)

def load_tasks_from_file(filename="tasks.json"):
    """Đọc danh sách công việc từ file JSON."""
    try:
        with open(filename, "r") as file:
            return json.load(file)
    except FileNotFoundError:
        return []

# Bài toán lập lịch
class ScheduleProblem(SearchProblem):
    def __init__(self, tasks):
        self.tasks = tasks
        self.schedule_full = False  # Thêm cờ để theo dõi trạng thái lịch
        super().__init__(initial_state=())

    def actions(self, state):
        return [task for task in self.tasks if task["id"] not in [s[0] for s in state]]

    def result(self, state, action):
        new_task_start = parse_time(action["start_time"])
        new_task_duration = action["duration"]

        for day_offset in range(7):  # Thử xếp vào 7 ngày trong tuần
            candidate_start = add_days(new_task_start, day_offset)
            candidate_end = candidate_start + timedelta(hours=new_task_duration)

            # Kiểm tra xung đột thời gian
            conflict = False
            for _, existing_start, existing_duration in state:
                existing_end = existing_start + timedelta(hours=existing_duration)
                if not (candidate_start >= existing_end or candidate_end <= existing_start):
                    conflict = True
                    break

            if not conflict:  # Nếu không xung đột
                new_task = (action["id"], candidate_start, new_task_duration)
                return state + (new_task,)

        # Nếu đã duyệt qua tất cả các ngày mà không tìm được chỗ trống
        self.schedule_full = True
        return state

    def is_goal(self, state):
        return len(state) == len(self.tasks)

    def heuristic(self, state):
        if not state:
            return len(self.tasks)  # Nếu không có công việc nào đã được lên lịch, trả về số lượng công việc

        # Tìm thời gian kết thúc muộn nhất
        max_end_time = max(
            task_start + timedelta(hours=task_duration)
            for _, task_start, task_duration in state
        )
        sunday = parse_time("23:59") + timedelta(days=6)  # Chủ nhật cuối cùng
        remaining_time = (sunday - max_end_time).total_seconds()

        # Tính toán số công việc còn lại
        remaining_tasks = len(self.tasks) - len(state)

        # Trả về tổng số giây còn lại cộng với số công việc còn lại
        return remaining_time + (remaining_tasks * 3600)  # Giả định mỗi công việc cần ít nhất 1 giờ

# Ứng dụng giao diện
class SchedulerApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Weekly Task Scheduler")
        self.setGeometry(100, 100, 800, 600)

        self.tasks = load_tasks_from_file()
        self.completed_tasks = []  # Danh sách công việc đã hoàn thành
        self.init_ui()
        self.update_calendar()

    def init_ui(self):
        layout = QVBoxLayout()

        # Form nhập công việc
        form_layout = QHBoxLayout()
        self.task_name_input = QLineEdit()
        self.task_name_input.setPlaceholderText("Task Name")
        self.start_time_input = QLineEdit()
        self.start_time_input.setPlaceholderText("Start Time (HH:MM)")
        self.duration_input = QLineEdit()
        self.duration_input.setPlaceholderText("Duration (hours)")
        self.add_task_button = QPushButton("Add Task")
        self.add_task_button.clicked.connect(self.add_task)

        form_layout.addWidget(self.task_name_input)
        form_layout.addWidget(self.start_time_input)
        form_layout.addWidget(self.duration_input)
        form_layout.addWidget(self.add_task_button)

        layout.addLayout(form_layout)

        # Bảng hiển thị lịch
        self.calendar_table = QTableWidget(24, 7)  # 24 giờ, 7 ngày
        self.calendar_table.setHorizontalHeaderLabels(["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"])
        self.calendar_table.setVerticalHeaderLabels([f"{hour}:00" for hour in range(24)])
        self.calendar_table.setSelectionMode(QAbstractItemView.SingleSelection)  # Chỉ cho phép chọn 1 ô
        layout.addWidget(self.calendar_table)

        # Bảng hiển thị công việc đã hoàn thành
        self.completed_table = QTableWidget(0, 2)  # 0 hàng, 2 cột
        self.completed_table.setHorizontalHeaderLabels(["Completed Task", "Completion Time"])
        layout.addWidget(self.completed_table)

        # Nút lưu công việc
        self.save_button = QPushButton("Save Tasks")
        self.save_button.clicked.connect(self.save_tasks)
        layout.addWidget(self.save_button)

        # Nút hoàn thành công việc
        self.complete_task_button = QPushButton("Complete Task")
        self.complete_task_button.clicked.connect(self.complete_task)
        layout.addWidget(self.complete_task_button)

        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)

    def add_task(self):
        try:
            task_name = self.task_name_input.text()
            start_time = self.start_time_input.text()
            duration = int(self.duration_input.text())

            start_time_dt = parse_time(start_time)
            start_hour = start_time_dt.hour
            start_day = start_time_dt.weekday()  # Không cần điều chỉnh

            # Tạo ID duy nhất cho task
            task_id = str(uuid.uuid4()) # Vẽ miếng dán công việc vào bảng
            for hour in range(duration):
                if start_hour + hour < 24:  # Kiểm tra không vượt quá 24 giờ
                    item = QTableWidgetItem(task_name)
                    item.setData(Qt.UserRole, task_id)  # Lưu ID vào item data
                    self.calendar_table.setItem(start_hour + hour, start_day, item)

            self.tasks.append({
                "id": task_id,  # Lưu ID duy nhất
                "name": task_name,
                "start_time": start_time,
                "duration": duration
            })
            self.schedule_tasks()  # Tự động lập lịch khi thêm công việc
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Invalid input: {str(e)}")

    def complete_task(self):
        selected_items = self.calendar_table.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, "No Selection", "Please select a task to mark as complete.")
            return

        # Lấy thông tin task từ ô được chọn
        selected_item = selected_items[0]
        task_name = selected_item.text()
        task_id = selected_item.data(Qt.UserRole)  # Lấy ID từ item data

        # Xóa task khỏi bảng lịch
        for r in range(self.calendar_table.rowCount()):
            for c in range(self.calendar_table.columnCount()):
                item = self.calendar_table.item(r, c)
                if item and item.text() == task_name and item.data(Qt.UserRole) == task_id:
                    self.calendar_table.setItem(r, c, QTableWidgetItem(""))

        # Thêm vào bảng completed
        completion_time = datetime.now().strftime("%H:%M %d/%m/%Y")
        self.completed_table.insertRow(self.completed_table.rowCount())
        self.completed_table.setItem(self.completed_table.rowCount() - 1, 0, QTableWidgetItem(task_name))
        self.completed_table.setItem(self.completed_table.rowCount() - 1, 1, QTableWidgetItem(completion_time))

        # Xóa task cụ thể
        self.tasks = [task for task in self.tasks if task["id"] != task_id]
        self.save_tasks()

    def schedule_tasks(self):
        try:
            problem = ScheduleProblem(self.tasks)
            solution = greedy(problem)

            if solution is None:
                QMessageBox.warning(self, "No Solution", "Could not schedule tasks!")
                return

            # Kiểm tra nếu lịch đã full
            if problem.schedule_full:
                QMessageBox.warning(self, "Schedule Full", 
                                    "No more time slots available. Cannot add more tasks this week.")
                return 
            
            self.calendar_table.clearContents()  # Xóa nội dung cũ
            for row, (task_id, start_time, duration) in enumerate(solution.state):
                # Tìm task tương ứng với task_id
                task = next((t for t in self.tasks if t["id"] == task_id), None)
                if task:
                    start_hour = start_time.hour
                    start_day = start_time.weekday()  # Không cần điều chỉnh
                    for hour in range(duration):
                        if start_hour + hour < 24:  # Kiểm tra không vượt quá 24 giờ
                            item = QTableWidgetItem(task['name'])
                            item.setData(Qt.UserRole, task_id)  # Lưu ID vào item data
                            self.calendar_table.setItem(start_hour + hour, start_day, item)

        except Exception as e:
            QMessageBox.critical(self, "Error", f"An error occurred: {str(e)}")

    def save_tasks(self):
        save_tasks_to_file(self.tasks)
        QMessageBox.information(self, "Success", "Tasks saved successfully!")

    def update_calendar(self):
        self.calendar_table.clearContents()  # Xóa nội dung cũ trước khi cập nhật
        for task in self.tasks:
            task_name = task["name"]
            start_time = parse_time(task["start_time"])
            duration = task["duration"]

            start_hour = start_time.hour
            start_day = start_time.weekday()  # Không cần điều chỉnh
            for hour in range(duration):
                if start_hour + hour < 24:  # Kiểm tra không vượt quá 24 giờ
                    item = QTableWidgetItem(task_name)
                    item.setData(Qt.UserRole, task['id'])  # Lưu ID vào item data
                    self.calendar_table.setItem(start_hour + hour, start_day, item)

# Chạy ứng dụng
if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = SchedulerApp()
    window.show()
    sys.exit(app.exec_())