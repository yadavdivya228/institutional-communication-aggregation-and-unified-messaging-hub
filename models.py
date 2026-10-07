from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
from bson.objectid import ObjectId

class User(UserMixin):
    def __init__(self, user_data):
        self.id = str(user_data.get('_id'))
        self.user_id = user_data.get('user_id')
        self.username = user_data.get('username')
        self.email = user_data.get('email')
        self.password_hash = user_data.get('password')
        self.role = user_data.get('role')
        self.department = user_data.get('department', '')
        self.year = user_data.get('year')
        self.created_at = user_data.get('created_at')
        self.last_login = user_data.get('last_login')
    
    def get_id(self):
        return self.user_id
    
    @staticmethod
    def create_user(mongo, username, email, password, role, department='', year=None):
        user_count = mongo.db.users.count_documents({})
        user_data = {
            'user_id': f'USER_{user_count + 1}',
            'username': username,
            'email': email,
            'password': generate_password_hash(password),
            'role': role,
            'department': department,
            'year': year,
            'created_at': datetime.utcnow(),
            'last_login': None
        }
        result = mongo.db.users.insert_one(user_data)
        user_data['_id'] = result.inserted_id
        return User(user_data)
    
    @staticmethod
    def get_by_email(mongo, email):
        user_data = mongo.db.users.find_one({'email': email})
        return User(user_data) if user_data else None
    
    @staticmethod
    def get_by_user_id(mongo, user_id):
        user_data = mongo.db.users.find_one({'user_id': user_id})
        return User(user_data) if user_data else None
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    
    def update_last_login(self, mongo):
        mongo.db.users.update_one(
            {'user_id': self.user_id},
            {'$set': {'last_login': datetime.utcnow()}}
        )

class Notice:
    @staticmethod
    def create_notice(mongo, title, content, priority, category, target_audience, 
                     created_by, attachments=None, expires_days=30):
        notice_count = mongo.db.notices.count_documents({})
        notice_data = {
            'notice_id': f'NOTICE_{notice_count + 1}',
            'title': title,
            'content': content,
            'priority': priority,
            'category': category,
            'target_audience': target_audience,
            'created_by': created_by,
            'attachments': attachments or [],
            'created_at': datetime.utcnow(),
            'expires_at': datetime.utcnow() + timedelta(days=expires_days),
            'is_active': True
        }
        mongo.db.notices.insert_one(notice_data)
        return notice_data
    
    @staticmethod
    def get_notices_for_user(mongo, user):
        notices = list(mongo.db.notices.find({'is_active': True}).sort('created_at', -1))
        user_notices = []
        
        for notice in notices:
            if 'all' in notice['target_audience']:
                user_notices.append(notice)
            elif user.role in notice['target_audience']:
                user_notices.append(notice)
            elif user.department in notice['target_audience']:
                user_notices.append(notice)
        
        return user_notices
    
    @staticmethod
    def get_all_notices(mongo):
        return list(mongo.db.notices.find({'is_active': True}).sort('created_at', -1))
    
    @staticmethod
    def get_notice_by_id(mongo, notice_id):
        return mongo.db.notices.find_one({'notice_id': notice_id})
    
    @staticmethod
    def update_notice(mongo, notice_id, updates):
        return mongo.db.notices.update_one({'notice_id': notice_id}, {'$set': updates})
    
    @staticmethod
    def delete_notice(mongo, notice_id):
        return mongo.db.notices.update_one({'notice_id': notice_id}, {'$set': {'is_active': False}})

class Acknowledgment:
    @staticmethod
    def mark_as_read(mongo, notice_id, user_id):
        existing = mongo.db.acknowledgments.find_one({'notice_id': notice_id, 'user_id': user_id})
        if existing:
            return False
        
        ack_data = {
            'notice_id': notice_id,
            'user_id': user_id,
            'read_at': datetime.utcnow(),
            'acknowledged': False,
            'acknowledged_at': None
        }
        mongo.db.acknowledgments.insert_one(ack_data)
        return True
    
    @staticmethod
    def mark_as_acknowledged(mongo, notice_id, user_id):
        result = mongo.db.acknowledgments.update_one(
            {'notice_id': notice_id, 'user_id': user_id},
            {'$set': {'acknowledged': True, 'acknowledged_at': datetime.utcnow()}},
            upsert=True
        )
        return result.modified_count > 0 or result.upserted_id is not None
    
    @staticmethod
    def get_missed_notices(mongo, user_id):
        user = User.get_by_user_id(mongo, user_id)
        user_notices = Notice.get_notices_for_user(mongo, user)
        user_acks = list(mongo.db.acknowledgments.find({'user_id': user_id}))
        ack_notice_ids = {ack['notice_id'] for ack in user_acks}
        missed = [notice for notice in user_notices if notice['notice_id'] not in ack_notice_ids]
        priority_order = {'critical': 0, 'important': 1, 'normal': 2}
        missed.sort(key=lambda x: (priority_order.get(x['priority'], 3), x['created_at']))
        return missed
    
    @staticmethod
    def get_read_status(mongo, notice_id, user_id):
        return mongo.db.acknowledgments.find_one({'notice_id': notice_id, 'user_id': user_id})

class Analytics:
    @staticmethod
    def get_notice_analytics(mongo, notice_id):
        notice = Notice.get_notice_by_id(mongo, notice_id)
        if not notice:
            return None
        
        all_users = list(mongo.db.users.find({}))
        target_count = len([u for u in all_users 
                           if 'all' in notice['target_audience'] 
                           or u['role'] in notice['target_audience']
                           or u.get('department') in notice['target_audience']])
        
        acks = list(mongo.db.acknowledgments.find({'notice_id': notice_id}))
        read_count = len(acks)
        acknowledged_count = len([a for a in acks if a.get('acknowledged')])
        
        read_percentage = (read_count / target_count * 100) if target_count > 0 else 0
        ack_percentage = (acknowledged_count / target_count * 100) if target_count > 0 else 0
        
        return {
            'notice_id': notice_id,
            'title': notice['title'],
            'priority': notice['priority'],
            'target_count': target_count,
            'read_count': read_count,
            'acknowledged_count': acknowledged_count,
            'read_percentage': round(read_percentage, 2),
            'acknowledgment_percentage': round(ack_percentage, 2)
        }
    
    @staticmethod
    def get_overall_analytics(mongo):
        total_notices = mongo.db.notices.count_documents({'is_active': True})
        notices = list(mongo.db.notices.find({'is_active': True}))
        priority_dist = {'critical': 0, 'important': 0, 'normal': 0}
        for notice in notices:
            priority = notice.get('priority', 'normal')
            priority_dist[priority] = priority_dist.get(priority, 0) + 1
        
        total_reads = mongo.db.acknowledgments.count_documents({})
        total_acknowledged = mongo.db.acknowledgments.count_documents({'acknowledged': True})
        
        return {
            'total_notices': total_notices,
            'total_reads': total_reads,
            'total_acknowledged': total_acknowledged,
            'priority_distribution': priority_dist
        }
    
    @staticmethod
    def get_user_engagement(mongo, user_id):
        user = User.get_by_user_id(mongo, user_id)
        user_notices = Notice.get_notices_for_user(mongo, user)
        total_applicable = len(user_notices)
        user_acks = list(mongo.db.acknowledgments.find({'user_id': user_id}))
        total_read = len(user_acks)
        total_acknowledged = len([a for a in user_acks if a.get('acknowledged')])
        engagement_score = (total_acknowledged / total_applicable * 100) if total_applicable > 0 else 0
        
        return {
            'user_id': user_id,
            'total_applicable_notices': total_applicable,
            'total_read': total_read,
            'total_acknowledged': total_acknowledged,
            'engagement_score': round(engagement_score, 2)
        }
