import sys
sys.path.insert(0, '/root/fanfic-platform')
from app import app, db, User, Post, Comment
from werkzeug.security import generate_password_hash

with app.app_context():
    # Create user if not exists
    user = User.query.filter_by(username='testlocal').first()
    if not user:
        user = User(username='testlocal', password_hash=generate_password_hash('test123'), bio='test')
        db.session.add(user)
        db.session.commit()
        print(f'User created: id={user.id}')

    # Create post
    post = Post(title='本地测试文章', content='测试内容', post_type='同人文', category='豚馒', user_id=user.id)
    db.session.add(post)
    db.session.commit()
    print(f'Post created: id={post.id}')

    # Add comment
    comment = Comment(content='测试评论', user_id=user.id, post_id=post.id)
    db.session.add(comment)
    db.session.commit()
    print(f'Comment created: id={comment.id}')

    # Verify
    print(f'Author: {post.author.username}')
    print(f'Comments count: {post.comments.count()}')
    print('DONE')
