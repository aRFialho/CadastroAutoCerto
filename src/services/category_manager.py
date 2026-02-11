"""Gerenciador de Categorias da Loja Web"""

import json
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from datetime import datetime

from ..core.models import CategoryItem
from ..utils.logger import get_logger

logger = get_logger("category_manager")


class CategoryManager:
    """Gerenciador de categorias da loja web com autenticação"""

    def __init__(self, db_path: Path, password: str):
        self.db_path = db_path
        self.password = password
        self.categories: List[CategoryItem] = []
        self._next_id = 1

        # Criar diretório se não existir
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        # Carregar categorias existentes
        self.load_categories()

    def _validate_password(self, provided_password: str) -> bool:
        """Valida senha para operações de modificação"""
        return provided_password == self.password

    def load_categories(self) -> bool:
        """Carrega categorias do arquivo JSON"""
        try:
            if not self.db_path.exists():
                logger.info(f"Arquivo de categorias não existe, criando: {self.db_path}")
                self._create_empty_db()
                return True

            with open(self.db_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # Converter JSON para objetos CategoryItem
            self.categories = [self._dict_to_category(item) for item in data]

            # Calcular próximo ID
            self._calculate_next_id()

            logger.success(f"✅ {len(self.categories)} categorias carregadas de {self.db_path}")
            return True

        except Exception as e:
            logger.error(f"❌ Erro ao carregar categorias: {e}")
            return False

    def save_categories(self) -> bool:
        """Salva categorias no arquivo JSON"""
        try:
            # Converter objetos CategoryItem para dict
            data = [self._category_to_dict(cat) for cat in self.categories]

            # Backup do arquivo atual
            if self.db_path.exists():
                backup_path = self.db_path.with_suffix(f'.backup_{datetime.now().strftime("%Y%m%d_%H%M%S")}.txt')
                self.db_path.rename(backup_path)
                logger.info(f"📦 Backup criado: {backup_path}")

            # Salvar novo arquivo
            with open(self.db_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            logger.success(f"✅ Categorias salvas em {self.db_path}")
            return True

        except Exception as e:
            logger.error(f"❌ Erro ao salvar categorias: {e}")
            return False

    def _dict_to_category(self, data: Dict) -> CategoryItem:
        """Converte dict para CategoryItem recursivamente"""
        children = [self._dict_to_category(child) for child in data.get('children', [])]
        return CategoryItem(
            name=data['name'],
            id=data['id'],
            status=data.get('status', 'Ativo'),
            children=children
        )

    def _category_to_dict(self, category: CategoryItem) -> Dict:
        """Converte CategoryItem para dict recursivamente"""
        return {
            'name': category.name,
            'id': category.id,
            'status': category.status,
            'children': [self._category_to_dict(child) for child in category.children]
        }

    def _calculate_next_id(self):
        """Calcula o próximo ID disponível"""
        max_id = 0

        def find_max_id(categories: List[CategoryItem]):
            nonlocal max_id
            for cat in categories:
                max_id = max(max_id, cat.id)
                find_max_id(cat.children)

        find_max_id(self.categories)
        self._next_id = max_id + 1

    def _create_empty_db(self):
        """Cria arquivo vazio de categorias"""
        with open(self.db_path, 'w', encoding='utf-8') as f:
            json.dump([], f, ensure_ascii=False, indent=2)

    def add_category(self, name: str, parent_id: Optional[int] = None, password: str = "") -> Tuple[bool, str]:
        """Adiciona nova categoria"""
        if not self._validate_password(password):
            return False, "❌ Senha incorreta"

        try:
            # Verificar se nome já existe no mesmo nível
            if self._name_exists(name, parent_id):
                return False, f"❌ Categoria '{name}' já existe neste nível"

            # Criar nova categoria
            new_category = CategoryItem(
                name=name,
                id=self._next_id,
                status="Ativo",
                children=[]
            )

            # Adicionar à categoria pai ou raiz
            if parent_id is None:
                self.categories.append(new_category)
            else:
                parent = self._find_category_by_id(parent_id)
                if not parent:
                    return False, f"❌ Categoria pai com ID {parent_id} não encontrada"
                parent.children.append(new_category)

            self._next_id += 1

            # Salvar
            if self.save_categories():
                logger.success(f"✅ Categoria '{name}' adicionada com ID {new_category.id}")
                return True, f"✅ Categoria '{name}' adicionada com sucesso (ID: {new_category.id})"
            else:
                return False, "❌ Erro ao salvar categoria"

        except Exception as e:
            logger.error(f"❌ Erro ao adicionar categoria: {e}")
            return False, f"❌ Erro ao adicionar categoria: {e}"

    def edit_category(self, category_id: int, new_name: str, password: str = "") -> Tuple[bool, str]:
        """Edita nome de uma categoria"""
        if not self._validate_password(password):
            return False, "❌ Senha incorreta"

        try:
            category = self._find_category_by_id(category_id)
            if not category:
                return False, f"❌ Categoria com ID {category_id} não encontrada"

            old_name = category.name
            category.name = new_name

            if self.save_categories():
                logger.success(f"✅ Categoria ID {category_id} renomeada de '{old_name}' para '{new_name}'")
                return True, f"✅ Categoria renomeada para '{new_name}'"
            else:
                return False, "❌ Erro ao salvar alteração"

        except Exception as e:
            logger.error(f"❌ Erro ao editar categoria: {e}")
            return False, f"❌ Erro ao editar categoria: {e}"

    def toggle_status(self, category_id: int, password: str = "") -> Tuple[bool, str]:
        """Alterna status de uma categoria (Ativo/Inativo)"""
        if not self._validate_password(password):
            return False, "❌ Senha incorreta"

        try:
            category = self._find_category_by_id(category_id)
            if not category:
                return False, f"❌ Categoria com ID {category_id} não encontrada"

            old_status = category.status
            category.status = "Inativo" if category.status == "Ativo" else "Ativo"

            if self.save_categories():
                logger.success(
                    f"✅ Status da categoria '{category.name}' alterado de '{old_status}' para '{category.status}'")
                return True, f"✅ Status alterado para '{category.status}'"
            else:
                return False, "❌ Erro ao salvar alteração"

        except Exception as e:
            logger.error(f"❌ Erro ao alterar status: {e}")
            return False, f"❌ Erro ao alterar status: {e}"

    def _find_category_by_id(self, category_id: int) -> Optional[CategoryItem]:
        """Busca categoria por ID recursivamente"""

        def search_recursive(categories: List[CategoryItem]) -> Optional[CategoryItem]:
            for cat in categories:
                if cat.id == category_id:
                    return cat
                result = search_recursive(cat.children)
                if result:
                    return result
            return None

        return search_recursive(self.categories)

    def _name_exists(self, name: str, parent_id: Optional[int]) -> bool:
        """Verifica se nome já existe no mesmo nível"""
        if parent_id is None:
            # Verificar no nível raiz
            return any(cat.name.lower() == name.lower() for cat in self.categories)
        else:
            # Verificar nos filhos da categoria pai
            parent = self._find_category_by_id(parent_id)
            if parent:
                return any(child.name.lower() == name.lower() for child in parent.children)
        return False

    def get_all_categories(self) -> List[CategoryItem]:
        """Retorna todas as categorias"""
        return self.categories

    def search_categories(self, search_term: str) -> List[CategoryItem]:
        """Busca categorias por nome"""
        results = []

        def search_recursive(categories: List[CategoryItem]):
            for cat in categories:
                if search_term.lower() in cat.name.lower():
                    results.append(cat)
                search_recursive(cat.children)

        search_recursive(self.categories)
        return results

    def get_category_path(self, category_id: int) -> Optional[str]:
        """Retorna o caminho completo de uma categoria (ex: 'Móveis > Poltronas > Decorativas')"""

        def find_path(categories: List[CategoryItem], path: List[str] = []) -> Optional[List[str]]:
            for cat in categories:
                current_path = path + [cat.name]
                if cat.id == category_id:
                    return current_path
                result = find_path(cat.children, current_path)
                if result:
                    return result
            return None

        path_list = find_path(self.categories)
        return " > ".join(path_list) if path_list else None

    def import_from_txt_file(self, txt_file_path: Path, password: str = "") -> Tuple[bool, str]:
        """Importa categorias de um arquivo TXT com estrutura JSON"""
        if not self._validate_password(password):
            return False, "❌ Senha incorreta"

        try:
            if not txt_file_path.exists():
                return False, f"❌ Arquivo não encontrado: {txt_file_path}"

            # Ler arquivo TXT
            with open(txt_file_path, 'r', encoding='utf-8') as f:
                content = f.read().strip()

            # Tentar parsear como JSON
            try:
                data = json.loads(content)
            except json.JSONDecodeError as e:
                return False, f"❌ Erro ao parsear JSON: {e}"

            # Backup das categorias atuais
            backup_categories = self.categories.copy()

            try:
                # Limpar categorias atuais
                self.categories = []

                # Converter e importar
                imported_count = 0
                for item in data:
                    category = self._dict_to_category(item)
                    self.categories.append(category)
                    imported_count += self._count_categories_recursive([category])

                # Recalcular próximo ID
                self._calculate_next_id()

                # Salvar
                if self.save_categories():
                    logger.success(f"✅ {imported_count} categorias importadas de {txt_file_path}")
                    return True, f"✅ {imported_count} categorias importadas com sucesso!"
                else:
                    # Restaurar backup em caso de erro
                    self.categories = backup_categories
                    return False, "❌ Erro ao salvar categorias importadas"

            except Exception as e:
                # Restaurar backup em caso de erro
                self.categories = backup_categories
                logger.error(f"Erro durante importação: {e}")
                return False, f"❌ Erro durante importação: {e}"

        except Exception as e:
            logger.error(f"Erro ao importar arquivo: {e}")
            return False, f"❌ Erro ao ler arquivo: {e}"

    def _count_categories_recursive(self, categories: List[CategoryItem]) -> int:
        """Conta categorias recursivamente"""
        count = len(categories)
        for cat in categories:
            count += self._count_categories_recursive(cat.children)
        return count

    def clear_all_categories(self, password: str = "") -> Tuple[bool, str]:
        """Limpa todas as categorias (para reimportação)"""
        if not self._validate_password(password):
            return False, "❌ Senha incorreta"

        try:
            # Backup
            backup_path = self.db_path.with_suffix(f'.backup_clear_{datetime.now().strftime("%Y%m%d_%H%M%S")}.txt')
            if self.db_path.exists():
                import shutil
                shutil.copy2(self.db_path, backup_path)
                logger.info(f"📦 Backup criado antes da limpeza: {backup_path}")

            # Limpar
            self.categories = []
            self._next_id = 1

            # Salvar
            if self.save_categories():
                logger.success("✅ Todas as categorias foram removidas")
                return True, "✅ Todas as categorias foram removidas com sucesso!"
            else:
                return False, "❌ Erro ao salvar após limpeza"

        except Exception as e:
            logger.error(f"Erro ao limpar categorias: {e}")
            return False, f"❌ Erro ao limpar categorias: {e}"