import os
import uuid
from datetime import datetime

from flask import (
    Flask, render_template, request, redirect, url_for,
    flash, jsonify, send_from_directory, session
)
from flask_sqlalchemy import SQLAlchemy
from flask_login import (
    LoginManager, UserMixin, login_user, logout_user,
    login_required, current_user
)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from werkzeug.middleware.proxy_fix import ProxyFix
from PIL import Image

# ── App Setup ──
app = Flask(__name__)

# Use env vars with sensible defaults for production and dev
app.config['SECRET_KEY'] = os.environ.get(
    'SECRET_KEY',
    os.urandom(24).hex()
)
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get(
    'DATABASE_URL',
    'sqlite:///fanfic.db'
)
# Render provides DATABASE_URL starting with postgres:// but SQLAlchemy needs postgresql://
if app.config['SQLALCHEMY_DATABASE_URI'] and app.config['SQLALCHEMY_DATABASE_URI'].startswith('postgres://'):
    app.config['SQLALCHEMY_DATABASE_URI'] = app.config['SQLALCHEMY_DATABASE_URI'].replace('postgres://', 'postgresql://', 1)

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max upload
app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(__file__), 'uploads')

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Proxy fix for running behind Nginx reverse proxy (local setup)
# On Render (cloud), no proxy prefix needed
if os.environ.get('PROXY_PREFIX'):
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'gate'
login_manager.login_message = '请先登录哦～'

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'bmp'}

# ── Post Types & Categories ──
POST_TYPES = ['捡手机', '同人文', '同人图']
SUBCATEGORIES = ['豚馒', '杰丞', '全穆', '困丞', '璐橙']

# ── Database Models ──

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    bio = db.Column(db.Text, default='这个人很懒，什么都没写～')
    avatar = db.Column(db.String(256), default='default_avatar.png')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    posts = db.relationship('Post', backref='author', lazy='dynamic', cascade='all, delete-orphan')
    feedbacks = db.relationship('Feedback', backref='author', lazy='dynamic', cascade='all, delete-orphan')
    forum_threads = db.relationship('ForumThread', backref='author', lazy='dynamic', cascade='all, delete-orphan')
    comments = db.relationship('Comment', backref='author', lazy='dynamic', cascade='all, delete-orphan')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Post(db.Model):
    __tablename__ = 'posts'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=True)
    post_type = db.Column(db.String(20), nullable=False)  # 捡手机 / 同人文 / 同人图
    category = db.Column(db.String(20), nullable=False)    # 豚馒 / 杰丞 ...
    image_path = db.Column(db.String(256), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    views = db.Column(db.Integer, default=0)

    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    comments = db.relationship('Comment', backref='post', lazy='dynamic', cascade='all, delete-orphan')


class Comment(db.Model):
    __tablename__ = 'comments'
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    post_id = db.Column(db.Integer, db.ForeignKey('posts.id'), nullable=False)


class Feedback(db.Model):
    __tablename__ = 'feedbacks'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=False)
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)


class ForumThread(db.Model):
    __tablename__ = 'forum_threads'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    reply_count = db.Column(db.Integer, default=0)

    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    replies = db.relationship('ForumReply', backref='thread', lazy='dynamic', cascade='all, delete-orphan')


class ForumReply(db.Model):
    __tablename__ = 'forum_replies'
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    thread_id = db.Column(db.Integer, db.ForeignKey('forum_threads.id'), nullable=False)


# ── Gate Secret ──
GATE_QUESTION = '公开日是？'
GATE_ANSWER = '10月06日'


# ── Helper Functions ──

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def save_upload(file):
    """Save uploaded image and return the filename."""
    if file and allowed_file(file.filename):
        ext = file.filename.rsplit('.', 1)[1].lower()
        filename = f"{uuid.uuid4().hex}.{ext}"
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)

        # Resize large images to save space
        try:
            img = Image.open(filepath)
            if max(img.size) > 1920:
                img.thumbnail((1920, 1920), Image.LANCZOS)
                img.save(filepath, optimize=True)
        except Exception:
            pass

        return filename
    return None


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


def check_gate():
    """Check if user has passed the gate."""
    return session.get('gate_passed', False)


# ── Routes ──

# ── Gate (Entry) ──
@app.route('/', methods=['GET', 'POST'])
def gate():
    if check_gate():
        return redirect(url_for('home'))

    if request.method == 'POST':
        answer = request.form.get('answer', '').strip()
        if answer == GATE_ANSWER:
            session['gate_passed'] = True
            flash('暗号正确！欢迎来到星辰小窝 ✨', 'success')
            return redirect(url_for('home'))
        else:
            flash('暗号不对哦，再想想？💭', 'error')

    return render_template('gate.html', question=GATE_QUESTION)


# ── Auth ──
@app.route('/login', methods=['GET', 'POST'])
def login():
    if not check_gate():
        return redirect(url_for('gate'))
    if current_user.is_authenticated:
        return redirect(url_for('home'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            login_user(user)
            next_page = request.args.get('next')
            flash(f'欢迎回来，{user.username}！🌸', 'success')
            return redirect(next_page or url_for('home'))
        flash('用户名或密码错误啦～', 'error')

    return render_template('login.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    if not check_gate():
        return redirect(url_for('gate'))
    if current_user.is_authenticated:
        return redirect(url_for('home'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        confirm = request.form.get('confirm', '')

        if not username or not password:
            flash('用户名和密码不能为空哦～', 'error')
        elif len(username) < 2 or len(username) > 20:
            flash('用户名长度需要在 2-20 个字符之间～', 'error')
        elif len(password) < 4:
            flash('密码至少需要 4 个字符～', 'error')
        elif password != confirm:
            flash('两次输入的密码不一致～', 'error')
        elif User.query.filter_by(username=username).first():
            flash('用户名已经被注册啦，换一个吧～', 'error')
        else:
            user = User(username=username)
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            flash('注册成功！快来开始创作吧 🎉', 'success')
            login_user(user)
            return redirect(url_for('home'))

    return render_template('register.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('已安全退出，下次见～👋', 'info')
    return redirect(url_for('gate'))


# ── Home ──
@app.route('/home')
def home():
    if not check_gate():
        return redirect(url_for('gate'))

    page = request.args.get('page', 1, type=int)

    # Latest posts across all types
    latest_posts = Post.query.order_by(Post.created_at.desc()).limit(12).all()

    # Posts by type (for overview)
    posts_by_type = {}
    for pt in POST_TYPES:
        posts_by_type[pt] = Post.query.filter_by(post_type=pt).order_by(
            Post.created_at.desc()
        ).limit(6).all()

    # Newest forum threads
    latest_threads = ForumThread.query.order_by(
        ForumThread.created_at.desc()
    ).limit(5).all()

    # Hot posts (most viewed)
    hot_posts = Post.query.order_by(Post.views.desc()).limit(6).all()

    # Stats
    total_users = User.query.count()
    total_posts = Post.query.count()
    total_threads = ForumThread.query.count()

    return render_template(
        'index.html',
        latest_posts=latest_posts,
        hot_posts=hot_posts,
        posts_by_type=posts_by_type,
        latest_threads=latest_threads,
        total_users=total_users,
        total_posts=total_posts,
        total_threads=total_threads,
        post_types=POST_TYPES,
    )


# ── Category / Browse ──
@app.route('/browse/<post_type>')
def browse_type(post_type):
    if not check_gate():
        return redirect(url_for('gate'))

    if post_type not in POST_TYPES:
        flash('分类不存在～', 'error')
        return redirect(url_for('home'))

    category = request.args.get('category')
    page = request.args.get('page', 1, type=int)
    sort = request.args.get('sort', 'newest')

    query = Post.query.filter_by(post_type=post_type)

    if category and category in SUBCATEGORIES:
        query = query.filter_by(category=category)

    if sort == 'views':
        query = query.order_by(Post.views.desc(), Post.created_at.desc())
    elif sort == 'oldest':
        query = query.order_by(Post.created_at.asc())
    else:  # newest
        query = query.order_by(Post.created_at.desc())

    posts = query.paginate(page=page, per_page=12, error_out=False)

    return render_template(
        'category.html',
        posts=posts,
        post_type=post_type,
        current_category=category,
        subcategories=SUBCATEGORIES,
        sort=sort,
    )


# ── Post CRUD ──
@app.route('/post/new', methods=['GET', 'POST'])
@login_required
def create_post():
    if not check_gate():
        return redirect(url_for('gate'))

    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        content = request.form.get('content', '').strip()
        post_type = request.form.get('post_type', '')
        category = request.form.get('category', '')

        if not title:
            flash('标题不能为空～', 'error')
        elif post_type not in POST_TYPES:
            flash('请选择正确的作品类型～', 'error')
        elif category not in SUBCATEGORIES:
            flash('请选择正确的分类～', 'error')
        else:
            image_path = None
            if 'image' in request.files:
                file = request.files['image']
                if file and file.filename:
                    image_path = save_upload(file)

            post = Post(
                title=title,
                content=content,
                post_type=post_type,
                category=category,
                image_path=image_path,
                user_id=current_user.id,
            )
            db.session.add(post)
            db.session.commit()
            flash('作品发布成功！🎉', 'success')
            return redirect(url_for('post_detail', post_id=post.id))

    return render_template(
        'create_post.html',
        post_types=POST_TYPES,
        subcategories=SUBCATEGORIES,
    )


@app.route('/post/<int:post_id>')
def post_detail(post_id):
    if not check_gate():
        return redirect(url_for('gate'))

    post = Post.query.get_or_404(post_id)
    post.views += 1
    db.session.commit()

    # More posts in same category
    related = Post.query.filter(
        Post.category == post.category,
        Post.id != post.id
    ).order_by(Post.created_at.desc()).limit(4).all()

    return render_template('post_detail.html', post=post, related=related)


@app.route('/post/<int:post_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_post(post_id):
    if not check_gate():
        return redirect(url_for('gate'))

    post = Post.query.get_or_404(post_id)
    if post.user_id != current_user.id:
        flash('只能编辑自己的作品哦～', 'error')
        return redirect(url_for('post_detail', post_id=post_id))

    if request.method == 'POST':
        post.title = request.form.get('title', '').strip()
        post.content = request.form.get('content', '').strip()

        if 'image' in request.files:
            file = request.files['image']
            if file and file.filename:
                # Delete old image
                if post.image_path:
                    old_path = os.path.join(app.config['UPLOAD_FOLDER'], post.image_path)
                    if os.path.exists(old_path):
                        os.remove(old_path)
                post.image_path = save_upload(file)

        db.session.commit()
        flash('作品已更新～✨', 'success')
        return redirect(url_for('post_detail', post_id=post.id))

    return render_template(
        'create_post.html',
        post=post,
        post_types=POST_TYPES,
        subcategories=SUBCATEGORIES,
        is_edit=True,
    )


@app.route('/post/<int:post_id>/delete', methods=['POST'])
@login_required
def delete_post(post_id):
    if not check_gate():
        return redirect(url_for('gate'))

    post = Post.query.get_or_404(post_id)
    if post.user_id != current_user.id:
        flash('只能删除自己的作品哦～', 'error')
        return redirect(url_for('post_detail', post_id=post_id))

    # Delete image file
    if post.image_path:
        img_path = os.path.join(app.config['UPLOAD_FOLDER'], post.image_path)
        if os.path.exists(img_path):
            os.remove(img_path)

    post_type = post.post_type
    db.session.delete(post)
    db.session.commit()
    flash('作品已删除～', 'info')
    return redirect(url_for('browse_type', post_type=post_type))


# ── Comments ──
@app.route('/post/<int:post_id>/comment', methods=['POST'])
@login_required
def add_comment(post_id):
    if not check_gate():
        return redirect(url_for('gate'))

    post = Post.query.get_or_404(post_id)
    content = request.form.get('content', '').strip()
    if content:
        comment = Comment(content=content, user_id=current_user.id, post_id=post_id)
        db.session.add(comment)
        db.session.commit()
        flash('评论成功！💬', 'success')
    return redirect(url_for('post_detail', post_id=post_id))


# ── Profile ──
@app.route('/profile/<username>')
def profile(username):
    if not check_gate():
        return redirect(url_for('gate'))

    user = User.query.filter_by(username=username).first_or_404()
    page = request.args.get('page', 1, type=int)

    posts = Post.query.filter_by(user_id=user.id).order_by(
        Post.created_at.desc()
    ).paginate(page=page, per_page=12, error_out=False)

    return render_template('profile.html', profile_user=user, posts=posts)


@app.route('/profile/edit', methods=['GET', 'POST'])
@login_required
def edit_profile():
    if not check_gate():
        return redirect(url_for('gate'))

    if request.method == 'POST':
        bio = request.form.get('bio', '').strip()
        if bio:
            current_user.bio = bio

        if 'avatar' in request.files:
            file = request.files['avatar']
            if file and file.filename:
                # Delete old avatar
                if current_user.avatar and current_user.avatar != 'default_avatar.png':
                    old_avatar = os.path.join(app.config['UPLOAD_FOLDER'], current_user.avatar)
                    if os.path.exists(old_avatar):
                        os.remove(old_avatar)
                filename = save_upload(file)
                if filename:
                    current_user.avatar = filename

        db.session.commit()
        flash('个人信息已更新～✨', 'success')
        return redirect(url_for('profile', username=current_user.username))

    return render_template('edit_profile.html')


# ── Feedback ──
@app.route('/feedback', methods=['GET', 'POST'])
@login_required
def feedback():
    if not check_gate():
        return redirect(url_for('gate'))

    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        content = request.form.get('content', '').strip()
        if title and content:
            fb = Feedback(title=title, content=content, user_id=current_user.id)
            db.session.add(fb)
            db.session.commit()
            flash('感谢你的反馈！我们会认真阅读的 💖', 'success')
            return redirect(url_for('feedback'))
        flash('标题和内容不能为空～', 'error')

    user_feedbacks = Feedback.query.filter_by(user_id=current_user.id).order_by(
        Feedback.created_at.desc()
    ).all()

    return render_template('feedback.html', feedbacks=user_feedbacks)


# ── Forum ──
@app.route('/forum')
def forum():
    if not check_gate():
        return redirect(url_for('gate'))

    page = request.args.get('page', 1, type=int)
    threads = ForumThread.query.order_by(
        ForumThread.updated_at.desc()
    ).paginate(page=page, per_page=15, error_out=False)

    return render_template('forum.html', threads=threads)


@app.route('/forum/new', methods=['GET', 'POST'])
@login_required
def create_thread():
    if not check_gate():
        return redirect(url_for('gate'))

    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        content = request.form.get('content', '').strip()
        if not title:
            flash('帖子标题不能为空～', 'error')
        elif not content:
            flash('帖子内容不能为空～', 'error')
        else:
            thread = ForumThread(title=title, content=content, user_id=current_user.id)
            db.session.add(thread)
            db.session.commit()
            flash('新帖子发布成功！🎉', 'success')
            return redirect(url_for('thread_detail', thread_id=thread.id))

    return render_template('create_thread.html')


@app.route('/forum/<int:thread_id>')
def thread_detail(thread_id):
    if not check_gate():
        return redirect(url_for('gate'))

    thread = ForumThread.query.get_or_404(thread_id)
    replies = ForumReply.query.filter_by(thread_id=thread_id).order_by(
        ForumReply.created_at.asc()
    ).all()

    return render_template('thread_detail.html', thread=thread, replies=replies)


@app.route('/forum/<int:thread_id>/reply', methods=['POST'])
@login_required
def add_reply(thread_id):
    if not check_gate():
        return redirect(url_for('gate'))

    thread = ForumThread.query.get_or_404(thread_id)
    content = request.form.get('content', '').strip()
    if content:
        reply = ForumReply(content=content, user_id=current_user.id, thread_id=thread_id)
        thread.reply_count += 1
        thread.updated_at = datetime.utcnow()
        db.session.add(reply)
        db.session.commit()
        flash('回复成功！💬', 'success')
    return redirect(url_for('thread_detail', thread_id=thread_id))


@app.route('/forum/<int:thread_id>/delete', methods=['POST'])
@login_required
def delete_thread(thread_id):
    if not check_gate():
        return redirect(url_for('gate'))

    thread = ForumThread.query.get_or_404(thread_id)
    if thread.user_id != current_user.id:
        flash('只能删除自己的帖子～', 'error')
        return redirect(url_for('thread_detail', thread_id=thread_id))

    db.session.delete(thread)
    db.session.commit()
    flash('帖子已删除～', 'info')
    return redirect(url_for('forum'))


# ── Static Files (Uploads) ──
@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)


# ── Search ──
@app.route('/search')
def search():
    if not check_gate():
        return redirect(url_for('gate'))

    q = request.args.get('q', '').strip()
    if not q:
        return redirect(url_for('home'))

    posts = Post.query.filter(
        db.or_(Post.title.contains(q), Post.content.contains(q))
    ).order_by(Post.created_at.desc()).limit(20).all()

    threads = ForumThread.query.filter(
        db.or_(ForumThread.title.contains(q), ForumThread.content.contains(q))
    ).order_by(ForumThread.created_at.desc()).limit(10).all()

    return render_template('search.html', q=q, posts=posts, threads=threads)


# ── Init DB ──
with app.app_context():
    db.create_all()
    # Create default avatar placeholder if not exists
    default_avatar_path = os.path.join(app.config['UPLOAD_FOLDER'], 'default_avatar.png')
    if not os.path.exists(default_avatar_path):
        img = Image.new('RGB', (200, 200), color=(180, 180, 220))
        img.save(default_avatar_path)


# ── Run ──
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_DEBUG', '0') == '1'
    app.run(host='0.0.0.0', port=port, debug=debug)
