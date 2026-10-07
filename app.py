from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_pymongo import PyMongo
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from config import Config
from models import User, Notice, Acknowledgment, Analytics

app = Flask(__name__)
app.config.from_object(Config)

mongo = PyMongo(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Please log in to access this page.'

@login_manager.user_loader
def load_user(user_id):
    return User.get_by_user_id(mongo, user_id)

@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        role = request.form.get('role')
        department = request.form.get('department', '')
        year = request.form.get('year', type=int)
        
        if password != confirm_password:
            flash('Passwords do not match!', 'error')
            return redirect(url_for('register'))
        
        if User.get_by_email(mongo, email):
            flash('Email already registered!', 'error')
            return redirect(url_for('register'))
        
        User.create_user(mongo, username, email, password, role, department, year)
        flash('Registration successful! Please login.', 'success')
        return redirect(url_for('login'))
    
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        user = User.get_by_email(mongo, email)
        
        if user and user.check_password(password):
            login_user(user, remember=True)
            user.update_last_login(mongo)
            flash(f'Welcome back, {user.username}!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid email or password!', 'error')
    
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out successfully.', 'success')
    return redirect(url_for('login'))

@app.route('/dashboard')
@login_required
def dashboard():
    user_notices = Notice.get_notices_for_user(mongo, current_user)[:5]
    missed_notices = Acknowledgment.get_missed_notices(mongo, current_user.user_id)
    user_engagement = Analytics.get_user_engagement(mongo, current_user.user_id)
    
    stats = {
        'total_notices': len(Notice.get_notices_for_user(mongo, current_user)),
        'unread_notices': len(missed_notices),
        'engagement_score': user_engagement['engagement_score']
    }
    
    return render_template('dashboard.html', notices=user_notices, 
                         missed_notices=missed_notices[:5], stats=stats)

@app.route('/notices')
@login_required
def notices():
    user_notices = Notice.get_notices_for_user(mongo, current_user)
    for notice in user_notices:
        ack = Acknowledgment.get_read_status(mongo, notice['notice_id'], current_user.user_id)
        notice['read_status'] = ack
    return render_template('notices.html', notices=user_notices)

@app.route('/notices/create', methods=['GET', 'POST'])
@login_required
def create_notice():
    if current_user.role not in ['admin', 'faculty']:
        flash('You do not have permission to create notices!', 'error')
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        title = request.form.get('title')
        content = request.form.get('content')
        priority = request.form.get('priority')
        category = request.form.get('category')
        target_audience = request.form.getlist('target_audience')
        expires_days = int(request.form.get('expires_days', 30))
        
        Notice.create_notice(mongo, title, content, priority, category, 
                           target_audience, current_user.user_id, expires_days=expires_days)
        flash('Notice created successfully!', 'success')
        return redirect(url_for('notices'))
    
    return render_template('create_notice.html', priorities=Config.PRIORITY_LEVELS,
                         categories=Config.CATEGORIES)

@app.route('/notices/<notice_id>/read', methods=['POST'])
@login_required
def mark_notice_read(notice_id):
    Acknowledgment.mark_as_read(mongo, notice_id, current_user.user_id)
    return jsonify({'success': True})

@app.route('/notices/<notice_id>/acknowledge', methods=['POST'])
@login_required
def acknowledge_notice(notice_id):
    Acknowledgment.mark_as_acknowledged(mongo, notice_id, current_user.user_id)
    flash('Notice acknowledged successfully!', 'success')
    return redirect(url_for('notices'))

@app.route('/notices/<notice_id>/delete', methods=['POST'])
@login_required
def delete_notice(notice_id):
    if current_user.role not in ['admin', 'faculty']:
        flash('You do not have permission to delete notices!', 'error')
        return redirect(url_for('notices'))
    Notice.delete_notice(mongo, notice_id)
    flash('Notice deleted successfully!', 'success')
    return redirect(url_for('notices'))

@app.route('/analytics')
@login_required
def analytics():
    if current_user.role not in ['admin', 'faculty']:
        flash('You do not have permission to view analytics!', 'error')
        return redirect(url_for('dashboard'))
    
    overall_analytics = Analytics.get_overall_analytics(mongo)
    all_notices = Notice.get_all_notices(mongo)
    notice_analytics = []
    for notice in all_notices[:10]:
        analytics_data = Analytics.get_notice_analytics(mongo, notice['notice_id'])
        if analytics_data:
            notice_analytics.append(analytics_data)
    
    return render_template('analytics.html', overall=overall_analytics,
                         notice_analytics=notice_analytics)

@app.route('/profile')
@login_required
def profile():
    engagement = Analytics.get_user_engagement(mongo, current_user.user_id)
    return render_template('profile.html', engagement=engagement)

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5005)
