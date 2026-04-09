# forum/routes.py
import re
import json
from flask import Blueprint, render_template, request, redirect, url_for, flash, abort, jsonify
from flask_login import login_required, current_user
from auth.models import User
# ✅ Добавлен импорт PostLike
from forum.models import Category, Topic, Post, Notification, CategorySubscription, TopicSubscription, PostLike
from extensions import db
from sqlalchemy import func, desc
from datetime import datetime, timedelta

# ✅ ИМПОРТ СИСТЕМЫ ПРАВ
from core.decorators import require_permission
from core.permissions import user_has_permission, ALL_PERMISSIONS

forum_bp = Blueprint('forum', __name__, url_prefix='/forum')

# ==========================================
# ХЕЛПЕРЫ (Вспомогательные функции)
# ==========================================

def _get_paginated_query(query, page, per_page=20):
    """Стандартная пагинация Flask-SQLAlchemy"""
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    return pagination.items, pagination

def _format_time(dt):
    """Красивое форматирование времени"""
    if not dt:
        return 'никогда'
    diff = (datetime.utcnow() - dt).total_seconds()
    if diff < 60:
        return 'только что'
    elif diff < 3600:
        return f'{int(diff/60)} мин. назад'
    elif diff < 86400:
        return f'{int(diff/3600)} ч. назад'
    elif diff < 604800:
        return f'{int(diff/86400)} дн. назад'
    else:
        return dt.strftime('%d.%m.%Y')

def _get_author_role(user):
    """Определяет ранг пользователя"""
    if user.id == 1:
        return {'title': 'Администратор', 'color': '#ff4757'}
    if user.topics.count() > 10 or user.posts.count() > 50:
        return {'title': 'Ветеран', 'color': '#ffa502'}
    return {'title': 'Игрок', 'color': '#9ca3af'}

def _generate_tags(title):
    """Автоматические теги на основе заголовка"""
    t = title.lower()
    tags = []
    if 'гайд' in t or 'урок' in t: tags.append({'name': 'Гайд', 'color': '#2ed573'})
    elif 'баг' in t or 'ошибк' in t: tags.append({'name': 'Баг', 'color': '#ff4757'})
    elif 'вопрос' in t or 'помощь' in t: tags.append({'name': 'Вопрос', 'color': '#1e90ff'})
    elif 'продам' in t or 'куплю' in t: tags.append({'name': 'Торговля', 'color': '#ffa502'})
    else: tags.append({'name': 'Обсуждение', 'color': '#5352ed'})
    return tags

# ==========================================
# РОУТЫ
# ==========================================

@forum_bp.route('/')
def index():
    """Главная страница форума"""
    if Category.query.count() == 0:
        default_cats = [
            {'title': 'Объявления', 'description': 'Новости проекта, правила и важная информация', 'icon': '📢', 'color': '#ff6b6b', 'order': 0},
            {'title': 'Общее', 'description': 'Свободное общение, вопросы и предложения', 'icon': '💬', 'color': '#4ecdc4', 'order': 1},
            {'title': 'РП-раздел', 'description': 'Ивенты, фракции и ролевые игры', 'icon': '🎭', 'color': '#a55eea', 'order': 2},
            {'title': 'Поддержка', 'description': 'Жалобы, заявки на разбан, тех. помощь', 'icon': '⚙️', 'color': '#26de81', 'order': 3},
            {'title': 'Творчество', 'description': 'Скриншоты, видео, гайды и фан-арт', 'icon': '🎨', 'color': '#fd9644', 'order': 4},
        ]
        for cat_data in default_cats:
            db.session.add(Category(**cat_data))
        db.session.commit()

    categories = Category.query.order_by(Category.order, Category.id).all()
    
    total_topics = db.session.scalar(db.select(func.count(Topic.id))) or 0
    total_posts = db.session.scalar(db.select(func.count(Post.id))) or 0
    total_users = db.session.scalar(db.select(func.count(User.id))) or 0
    
    online_threshold = datetime.utcnow() - timedelta(minutes=15)
    online_users = db.session.scalar(
        db.select(func.count(User.id)).filter(User.last_login >= online_threshold)
    ) or 1

    categories_data = []
    for cat in categories:
        stats = cat.get_stats()
        categories_data.append({
            'id': cat.id,
            'icon': cat.icon,
            'title': cat.title,
            'description': cat.description,
            'topics': stats['topics'],
            'posts': stats['posts'],
            'last_post': cat.get_last_post(),
            'color': cat.color
        })

    return render_template('forum/index.html',
                           categories=categories_data,
                           stats={'total_topics': total_topics, 'total_posts': total_posts, 'online_now': online_users},
                           total_users=total_users)

@forum_bp.route('/category/<int:category_id>')
def category(category_id):
    """Страница категории"""
    category = Category.query.get_or_404(category_id)
    
    page = request.args.get('page', 1, type=int)
    sort_by = request.args.get('sort', 'updated')
    filter_by = request.args.get('filter', 'all')
    search_q = request.args.get('q', '').strip()

    query = Topic.query.filter_by(category_id=category_id)

    if search_q:
        query = query.filter(Topic.title.ilike(f'%{search_q}%'))

    if filter_by == 'pinned':
        query = query.filter_by(is_pinned=True)
    elif filter_by == 'solved':
        solved_ids = db.session.query(Post.topic_id).filter_by(is_solution=True).distinct()
        query = query.filter(Topic.id.in_(solved_ids))

    if sort_by == 'created':
        query = query.order_by(desc(Topic.is_pinned), desc(Topic.created_at))
    elif sort_by == 'views':
        query = query.order_by(desc(Topic.is_pinned), desc(Topic.views))
    else:
        query = query.order_by(desc(Topic.is_pinned), desc(Topic.last_post_at))

    per_page = 15
    topics, pagination = _get_paginated_query(query, page, per_page)

    topics_data = []
    for topic in topics:
        posts_count = max(0, topic.posts.count() - 1)
        last_post = topic.posts.order_by(desc(Post.created_at)).first()
        first_post = topic.posts.order_by(Post.created_at).first()

        is_hot = topic.views > 50 or posts_count > 10
        is_new = (datetime.utcnow() - topic.created_at).total_seconds() < 86400

        preview = ""
        if first_post:
            clean_text = re.sub(r'<[^>]+>', '', first_post.content)
            preview = clean_text[:140] + '...' if len(clean_text) > 140 else clean_text

        topics_data.append({
            'id': topic.id,
            'title': topic.title,
            'preview': preview,
            'tags': _generate_tags(topic.title),
            'is_hot': is_hot,
            'is_new': is_new,
            'author': {
                'username': topic.author.username,
                'avatar': topic.author.avatar,
                'is_online': (datetime.utcnow() - topic.author.last_login) < timedelta(minutes=15),
                'role': _get_author_role(topic.author)
            },
            'created_at': topic.created_at,
            'views': topic.views,
            'replies': posts_count,
            'is_pinned': topic.is_pinned,
            'is_locked': topic.is_locked,
            'has_solution': any(post.is_solution for post in topic.posts),
            'last_post': {
                'author': last_post.author.username if last_post else topic.author.username,
                'time': _format_time(last_post.created_at if last_post else topic.created_at)
            } if last_post else None
        })

    return render_template('forum/category.html',
                           category=category,
                           topics=topics_data,
                           pagination=pagination,
                           current_sort=sort_by,
                           current_filter=filter_by,
                           category_stats=category.get_stats(),
                           search_q=search_q,
                           CategorySubscription=CategorySubscription)

@forum_bp.route('/category/<int:category_id>/new', methods=['GET', 'POST'])
@login_required
@require_permission('topic.create', redirect_to='forum.category', message='❌ У вас нет прав для создания тем в этом разделе')
def create_topic(category_id):
    """Создание темы в категории"""
    category = Category.query.get_or_404(category_id)
    
    if category.title.lower() in ['объявления', 'объявление', 'announcements', 'announce']:
        if not user_has_permission(current_user, 'topic.create_in_announce'):
            flash('❌ Публикация в разделе "Объявления" доступна только модераторам и администрации', 'error')
            return redirect(url_for('forum.category', category_id=category_id))

    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        content = request.form.get('content', '').strip()

        if not title or len(title) < 5:
            flash('Заголовок: минимум 5 символов', 'error')
        elif not content or len(content) < 10:
            flash('Текст: минимум 10 символов', 'error')
        else:
            topic = Topic(
                title=title,
                category_id=category_id,
                author_id=current_user.id,
                created_at=datetime.utcnow(),
                last_post_at=datetime.utcnow()
            )
            db.session.add(topic)
            db.session.flush()

            post = Post(
                topic_id=topic.id,
                author_id=current_user.id,
                content=content,
                created_at=datetime.utcnow()
            )
            db.session.add(post)
            db.session.commit()

            flash('🎉 Тема создана!', 'success')
            return redirect(url_for('forum.topic', topic_id=topic.id))

    can_pin = user_has_permission(current_user, 'topic.pin')
    
    return render_template('forum/create_topic.html', 
                           category=category,
                           can_pin=can_pin)

@forum_bp.route('/topic/<int:topic_id>')
def topic(topic_id):
    """Просмотр темы"""
    topic_obj = Topic.query.get_or_404(topic_id)
    page = request.args.get('page', 1, type=int)

    topic_obj.views += 1
    db.session.commit()

    per_page = 15
    posts_query = Post.query.filter_by(topic_id=topic_id).order_by(Post.created_at)
    posts, pagination = _get_paginated_query(posts_query, page, per_page)

    posts_data = []
    for idx, post in enumerate(posts):
        posts_data.append({
            'id': post.id,
            'content': post.content,
            'is_solution': post.is_solution,
            'created_at': post.created_at,
            'index': idx + 1 + ((page-1)*per_page),
            'author': {
                'username': post.author.username,
                'avatar': post.author.avatar,
                'is_online': (datetime.utcnow() - post.author.last_login) < timedelta(minutes=15),
                'role': _get_author_role(post.author),
                'join_date': post.author.created_at
            },
            'can_edit': (post.author_id == current_user.id and user_has_permission(current_user, 'post.edit_own')) or 
                       user_has_permission(current_user, 'post.edit_any'),
            'can_delete': (post.author_id == current_user.id and user_has_permission(current_user, 'post.delete_own')) or 
                         user_has_permission(current_user, 'post.delete_any')
        })

    all_categories = Category.query.order_by(Category.order).all()

    return render_template('forum/topic.html',
                           topic=topic_obj,
                           posts=posts_data,
                           pagination=pagination,
                           category=topic_obj.category,
                           all_categories=all_categories,
                           can_reply=user_has_permission(current_user, 'post.create') if current_user.is_authenticated else False,
                           can_pin=user_has_permission(current_user, 'topic.pin'),
                           can_lock=user_has_permission(current_user, 'topic.lock'),
                           can_delete_topic=user_has_permission(current_user, 'topic.delete_any'),
                           can_move=user_has_permission(current_user, 'topic.move'))

# ==========================================
# 🔔 ПОДПИСКИ НА РАЗДЕЛЫ И ТЕМЫ
# ==========================================

@forum_bp.route('/category/<int:category_id>/subscribe', methods=['POST'])
@login_required
def toggle_category_subscription(category_id):
    """Подписка/отписка от раздела (категории)"""
    category = Category.query.get_or_404(category_id)
    
    is_subscribed = CategorySubscription.toggle_subscription(
        current_user.id, category_id
    )
    
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({
            'success': True,
            'subscribed': is_subscribed,
            'message': f'{"✅ Подписка оформлена" if is_subscribed else "❌ Вы отписались"}'
        })
    else:
        flash(
            f'{"✅ Вы подписались на раздел" if is_subscribed else "❌ Вы отписались от раздела"}',
            'success' if is_subscribed else 'info'
        )
        return redirect(url_for('forum.category', category_id=category_id))

@forum_bp.route('/topic/<int:topic_id>/subscribe', methods=['POST'])
@login_required
def toggle_topic_subscription(topic_id):
    """Подписка/отписка от темы"""
    topic = Topic.query.get_or_404(topic_id)
    
    is_subscribed = TopicSubscription.toggle_subscription(
        current_user.id, topic_id
    )
    
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({
            'success': True,
            'subscribed': is_subscribed,
            'message': f'{"✅ Вы подписаны на тему" if is_subscribed else "❌ Вы отписались от темы"}'
        })
    else:
        flash(
            f'{"✅ Вы подписались на тему" if is_subscribed else "❌ Вы отписались от темы"}',
            'success' if is_subscribed else 'info'
        )
        return redirect(url_for('forum.topic', topic_id=topic_id))

# ==========================================
# ❤️ ЛАЙКИ И РЕПУТАЦИЯ
# ==========================================

@forum_bp.route('/post/<int:post_id>/like', methods=['POST'])
@login_required
def toggle_like(post_id):
    """AJAX-эндпоинт для переключения лайка"""
    post = Post.query.get_or_404(post_id)
    
    is_liked, like_count = PostLike.toggle_like(current_user.id, post_id)
    author_reputation = PostLike.get_user_reputation(post.author_id)
    
    return jsonify({
        'success': True,
        'liked': is_liked,
        'like_count': like_count,
        'author_reputation': author_reputation,
        'is_popular': author_reputation >= 100
    })

# ==========================================
# 🔧 ДЕЙСТВИЯ С ТЕМАМИ (с проверкой прав)
# ==========================================

@forum_bp.route('/topic/<int:topic_id>/pin', methods=['POST'])
@login_required
@require_permission('topic.pin', message='❌ Только модераторы могут закреплять темы')
def pin_topic(topic_id):
    topic = Topic.query.get_or_404(topic_id)
    
    if topic.category.title.lower() in ['объявления'] and not user_has_permission(current_user, 'topic.create_in_announce'):
        flash('❌ Недостаточно прав для этого раздела', 'error')
        return redirect(url_for('forum.topic', topic_id=topic_id))
    
    topic.is_pinned = not topic.is_pinned
    db.session.commit()
    
    action = "закреплена" if topic.is_pinned else "откреплена"
    flash(f'✅ Тема {action}', 'success')
    return redirect(url_for('forum.topic', topic_id=topic_id))

@forum_bp.route('/topic/<int:topic_id>/lock', methods=['POST'])
@login_required
@require_permission('topic.lock', message='❌ Только модераторы могут закрывать темы')
def lock_topic(topic_id):
    topic = Topic.query.get_or_404(topic_id)
    topic.is_locked = not topic.is_locked
    db.session.commit()
    
    action = "закрыта" if topic.is_locked else "открыта"
    flash(f'✅ Тема {action}', 'success')
    return redirect(url_for('forum.topic', topic_id=topic_id))

@forum_bp.route('/topic/<int:topic_id>/delete', methods=['POST'])
@login_required
@require_permission('topic.delete_any', message='❌ Только модераторы могут удалять темы')
def delete_topic(topic_id):
    topic = Topic.query.get_or_404(topic_id)
    
    if topic.author_id != current_user.id and not user_has_permission(current_user, 'topic.delete_any'):
        flash('❌ Можно удалять только свои темы', 'error')
        return redirect(url_for('forum.topic', topic_id=topic_id))
    
    title = topic.title
    db.session.delete(topic)  # Каскад удалит посты и лайки
    db.session.commit()
    
    flash(f'✅ Тема "{title}" удалена', 'success')
    return redirect(url_for('forum.category', category_id=topic.category_id))

@forum_bp.route('/topic/<int:topic_id>/move', methods=['POST'])
@login_required
@require_permission('topic.move', message='❌ Только модераторы могут переносить темы')
def move_topic(topic_id):
    topic = Topic.query.get_or_404(topic_id)
    new_category_id = request.form.get('category_id', type=int)
    
    if not new_category_id:
        flash('❌ Выберите раздел для переноса', 'error')
        return redirect(url_for('forum.topic', topic_id=topic_id))
    
    old_cat = topic.category.title
    topic.category_id = new_category_id
    db.session.commit()
    
    flash(f'✅ Тема перенесена из "{old_cat}" в "{topic.category.title}"', 'success')
    return redirect(url_for('forum.topic', topic_id=topic_id))

# ==========================================
# 💬 ДЕЙСТВИЯ С ПОСТАМИ
# ==========================================

@forum_bp.route('/topic/<int:topic_id>/reply', methods=['POST'])
@login_required
@require_permission('post.create', message='❌ У вас нет прав для ответа в темах')
def reply_to_topic(topic_id):
    topic = Topic.query.get_or_404(topic_id)
    
    if topic.is_locked and not user_has_permission(current_user, 'topic.lock'):
        flash('❌ Тема закрыта для ответов', 'error')
        return redirect(url_for('forum.topic', topic_id=topic_id))
    
    content = request.form.get('content', '').strip()
    if not content or len(content) < 3:
        flash('⚠️ Сообщение слишком короткое', 'warning')
        return redirect(url_for('forum.topic', topic_id=topic_id))
    
    post = Post(
        topic_id=topic_id,
        author_id=current_user.id,
        content=content,
        created_at=datetime.utcnow()
    )
    db.session.add(post)
    
    topic.last_post_at = datetime.utcnow()
    
    if topic.author_id != current_user.id:
        Notification.create_reply_notification(
            user_id=topic.author_id,
            topic_id=topic_id,
            post_id=post.id,
            from_user_id=current_user.id,
            post_preview=content[:100]
        )
    
    db.session.commit()
    flash('✅ Ответ опубликован', 'success')
    return redirect(url_for('forum.topic', topic_id=topic_id, page='last'))

@forum_bp.route('/post/<int:post_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_post(post_id):
    post = Post.query.get_or_404(post_id)
    
    is_own = post.author_id == current_user.id
    can_edit = (is_own and user_has_permission(current_user, 'post.edit_own')) or \
               user_has_permission(current_user, 'post.edit_any')
    
    if not can_edit:
        flash('❌ Недостаточно прав для редактирования этого сообщения', 'error')
        return redirect(url_for('forum.topic', topic_id=post.topic_id))
    
    if request.method == 'POST':
        content = request.form.get('content', '').strip()
        if not content:
            flash('⚠️ Сообщение не может быть пустым', 'warning')
        else:
            post.content = content
            db.session.commit()
            flash('✅ Сообщение обновлено', 'success')
            return redirect(url_for('forum.topic', topic_id=post.topic_id))
    
    return render_template('forum/edit_post.html', post=post, topic=post.topic)

@forum_bp.route('/post/<int:post_id>/delete', methods=['POST'])
@login_required
@require_permission('post.delete_any', message='❌ Недостаточно прав для удаления')
def delete_post(post_id):
    """Удаление поста с очисткой связанных лайков"""
    post = Post.query.get_or_404(post_id)
    topic_id = post.topic_id
    
    if post.author_id != current_user.id and not user_has_permission(current_user, 'post.delete_any'):
        flash('❌ Можно удалять только свои сообщения', 'error')
        return redirect(url_for('forum.topic', topic_id=topic_id))
    
    # ✅ FIX: Сначала удаляем все лайки этого поста, чтобы избежать ошибки IntegrityError
    PostLike.query.filter_by(post_id=post_id).delete()
    
    # Если это первый пост в теме — удаляем всю тему
    first_post = Post.query.filter_by(topic_id=topic_id).order_by(Post.created_at).first()
    if first_post and first_post.id == post_id:
        topic = Topic.query.get(topic_id)
        if topic:
            db.session.delete(topic)  # Каскад удалит остальные посты
    else:
        db.session.delete(post)
    
    db.session.commit()
    flash('✅ Сообщение удалено', 'success')
    return redirect(url_for('forum.topic', topic_id=topic_id))

@forum_bp.route('/post/<int:post_id>/solution', methods=['POST'])
@login_required
def toggle_solution(post_id):
    post = Post.query.get_or_404(post_id)
    topic = Topic.query.get_or_404(post.topic_id)
    
    is_author = topic.author_id == current_user.id
    is_mod = user_has_permission(current_user, 'mod.handle_reports')
    
    if not (is_author or is_mod):
        flash('❌ Только автор темы или модератор может отметить решение', 'error')
        return redirect(url_for('forum.topic', topic_id=topic.id))
    
    post.is_solution = not post.is_solution
    db.session.commit()
    
    action = "отмечено" if post.is_solution else "снято"
    flash(f'✅ Решение {action}', 'success')
    return redirect(url_for('forum.topic', topic_id=topic.id))

# ==========================================
# 📜 ПРАВИЛА ФОРУМА
# ==========================================

@forum_bp.route('/rules')
def rules():
    """Страница правил форума"""
    return render_template('forum/rules.html')

# ==========================================
# 🔍 ПОИСК
# ==========================================

@forum_bp.route('/search')
def search():
    query = request.args.get('q', '').strip()
    page = request.args.get('page', 1, type=int)
    
    if not query or len(query) < 3:
        flash('⚠️ Введите минимум 3 символа для поиска', 'warning')
        return redirect(url_for('forum.index'))
    
    topics = Topic.query.filter(
        Topic.title.ilike(f'%{query}%')
    ).order_by(desc(Topic.created_at)).paginate(page=page, per_page=20, error_out=False)
    
    return render_template('forum/search.html',
                           query=query,
                           topics=topics.items,
                           pagination=topics,
                           results_count=topics.total)