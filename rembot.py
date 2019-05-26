import time
import telebot
import sched
import datetime
import dateparser
import logging
import threading
import uuid

logging_level = logging.DEBUG
logger = logging.getLogger("rmndrBot" if __name__ == "__main__" else __name__)
c_handler = logging.StreamHandler()
logger.setLevel(logging_level)
c_handler.setLevel(logging_level)
c_format = logging.Formatter('%(asctime)s - %(threadName)s - %(levelname)s - %(message)s')
c_handler.setFormatter(c_format)
logger.addHandler(c_handler)

with open('apikey.txt', 'r') as f:
    apikey = f.readline()

contact_data = 'example@example.com'
bot = telebot.TeleBot(apikey)
tasks = {}
tasks_mutex_dict = {}
user_threads = {}
# s = sched.scheduler(time.time, time.sleep)


from dateparser.date import DateDataParser
class MiracleDateParser(DateDataParser):
    def __init__(self):
        super().__init__(languages=['en', 'ru'])
    def get_date_data(self, date_string, date_formats=None):
        parsed = super().get_date_data(date_string, date_formats)
        if not parsed['date_obj']:
            return None
        return parsed
    
SupercoolMiracleDateParserInstance = MiracleDateParser()

def dummy_time():
    dt = datetime.datetime.now()
    td = datetime.timedelta(seconds=5)
    dt += td
    return dt   

def message_to_user(user_id, message):
    bot.send_message(user_id, message)

def new_task(user_id, task):
    if user_id in tasks:
        tasks[user_id].append(task)
        tasks_mutex_dict[user_id].acquire() # synchronized
        tasks[user_id] = sorted(tasks[user_id], key=lambda task: task.scheduled_time)
        tasks_mutex_dict[user_id].release()
    else:
        tasks[user_id] = [task]
        tasks_mutex_dict[user_id] = threading.Lock()
        new_user(user_id)
    
def new_user(user_id, refresh_interval=5):
    new_thread = User_Thread(user_id, refresh_interval)
    user_threads[user_id] = (new_thread, True)
    logger.info("New user, id: %d!" % user_id)
    new_thread.start()
#     message_to_user(user_id, "Welcome to ReminderBot. We hope you will enjoy using it!")

class Task(object):
    def __init__(self, user_id, message_text, parser):
        self.parser = parser
        try:
            self.scheduled_time, self.content = self.parse_time_and_content(message_text)
        except:
            raise Exception('wrong format')
        self.creation_timestamp = datetime.datetime.now()
        self.user_id = user_id
        self.id = uuid.uuid4()
        logger.debug("New task id %s for user %d scheduled for %s." % (str(id), self.user_id, str(self.scheduled_time)))
    
    def parse_time_and_content(self, message_text):
        start_time = len(message_text.split()) if len(message_text.split()) < 6 else 5
        for i in range(start_time):
            parsed_time = self.parser.get_date_data(' '.join(message_text.split()[0:i]))
            if parsed_time:
                scheduled_time = parsed_time['date_obj']
                text = ' '.join(message_text.split()[i:])
            else:
                continue
        if scheduled_time:
            return scheduled_time, text
        else:
            raise Exception('wrong format')
    
    def execute(self):
        message_to_user(self.user_id, self.content)
        
# one per user_id
class User_Thread(threading.Thread):
    def __init__(self, user_id, refresh_interval):
        threading.Thread.__init__(self)
        self.user_id = user_id
        self.tasks_list = tasks[user_id]
        self.tasks_mutex = tasks_mutex_dict[user_id]
        self.refresh_interval = refresh_interval
        self.scheduler = sched.scheduler()
        
    def run(self):
        logger.info("thread started!")
        while user_threads[self.user_id][1]:
            self.schedule()
        logger.info("thread for user id %d finished." % self.user_id)
        
    def schedule(self):
        self.tasks_mutex.acquire() # synchronized
        self.tasks_list = tasks[self.user_id]
        if self.tasks_list:
            # logger.debug("Tasks_list: %s" % str(self.tasks_list))
            time_left = self.tasks_list[0].scheduled_time - datetime.timedelta(hours=3) - datetime.datetime.utcnow()
            if time_left.total_seconds() < self.refresh_interval:
                interval = time_left.total_seconds()
            else:
                interval = self.refresh_interval
        else:
            interval = self.refresh_interval
        self.tasks_mutex.release()
        self.scheduler.enter(interval, 1, self.clear_tasks)
#         logger.debug("Scheduler queue: %s" % str(self.scheduler.queue))
        self.scheduler.run()
        return
        
    def clear_tasks(self):
        self.tasks_mutex.acquire() # synchronized
        if(self.tasks_list):
            if self.tasks_list[0].scheduled_time < datetime.datetime.now():
                logger.debug("Popping task scheduled for %s for user id %d" % (str(self.tasks_list[0].scheduled_time), self.user_id))
                task = self.tasks_list.pop(0)
                task.execute()
        self.tasks_mutex.release()

@bot.message_handler(commands=['help',])
def send_welcome(message):
    instructions  = """Hi!\nSend me a message like \"Tomorrow 18:00 Dinner with Jack\" and I'll remind you at the time you specified!\nPlease report any problems at %s""" % contact_data
    bot.reply_to(message, instructions)
    
@bot.message_handler(commands=['tasks',])
def display_tasks(message):
    user_id = message.from_user.id
    if user_id not in tasks.keys():
        message_to_user(user_id, 'You have not created a task yet!')
        return
    tasks_for_user = tasks[user_id]
    result = [str(task.scheduled_time) + ' ' + str(task.content) for task in tasks_for_user]
    message_to_user(user_id, '\n'.join(result))
        
@bot.message_handler(content_types=['text'])
def get_text_messages(message):
    in_text = message.text
    user_id = message.from_user.id
    logger.debug("Received message %s from user_id %d." % (in_text, user_id))
    try:
        t = Task(user_id, in_text,SupercoolMiracleDateParserInstance)
    except Exception as e:
        message_to_user(user_id, "u wot m8")
        logger.warn("Illegal message format from user id %d" % user_id)
        return
    new_task(user_id, t)
    message_to_user(user_id, "New reminder scheduled for %s." % str(t.scheduled_time))
    logger.debug("Task queue for user %d: %s." % (user_id, str([task.id for task in tasks[user_id]])))

bot.polling(none_stop=True, interval=1)

