"""Base de datos local con el historial de facturas emitidas."""

from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    create_engine,
)
from sqlalchemy.orm import declarative_base, joinedload, relationship, sessionmaker

from config import DB_PATH

engine = create_engine(f"sqlite:///{DB_PATH.as_posix()}")
Base = declarative_base()
Session = sessionmaker(bind=engine, expire_on_commit=False)

TIPOS_DE_DOCUMENTO = ("CUIL", "CUIT", "DNI")
CONDICIONES_IVA = (
    "Consumidor Final",
    "Iva Responsable Inscripto",
    "Iva Sujeto Exento",
)


class Meta(Base):
    # pylint: disable=too-few-public-methods
    """Indica si la base de datos ya fue inicializada."""

    __tablename__ = "meta"
    id = Column(Integer, primary_key=True)
    inicializado = Column(Boolean, default=False)


class TiposDeDocumentos(Base):
    # pylint: disable=too-few-public-methods
    """Tipos de documento del cliente."""

    __tablename__ = "TiposDeDocumentos"

    id = Column(Integer, primary_key=True, autoincrement=True)
    nombre_de_tipo = Column(String, nullable=False)


class CondicionFrenteIva(Base):
    # pylint: disable=too-few-public-methods
    """Condiciones frente al IVA del cliente."""

    __tablename__ = "CondicionFrenteIva"

    id = Column(Integer, primary_key=True, autoincrement=True)
    nombre_de_condicion = Column(String, nullable=False)


class Facturas(Base):
    # pylint: disable=too-few-public-methods
    """Factura emitida."""

    __tablename__ = "Facturas"

    id = Column(Integer, primary_key=True, autoincrement=True)
    id_cliente = Column(String, nullable=True)
    tipo_de_documento_id = Column(
        String, ForeignKey("TiposDeDocumentos.id"), nullable=False
    )
    condicion_iva = Column(String, ForeignKey("CondicionFrenteIva.id"), nullable=False)
    productos = Column(JSON, nullable=False)
    valor_total = Column(Float(2), nullable=False)
    fecha = Column(DateTime, default=datetime.now)

    tipo_de_documento = relationship("TiposDeDocumentos")
    condicion_iva_rel = relationship("CondicionFrenteIva")


def inicializar_si_necesario():
    """Crea las tablas y carga los datos de referencia la primera vez."""
    Base.metadata.create_all(engine)
    with Session() as session:
        meta = session.query(Meta).first()
        if meta is None:
            meta = Meta(inicializado=False)
            session.add(meta)
        if not meta.inicializado:
            session.add_all(
                TiposDeDocumentos(nombre_de_tipo=nombre)
                for nombre in TIPOS_DE_DOCUMENTO
            )
            session.add_all(
                CondicionFrenteIva(nombre_de_condicion=nombre)
                for nombre in CONDICIONES_IVA
            )
            meta.inicializado = True
        session.commit()


def guardar_factura(id_cliente, tipo_documento, condicion_iva, productos, total):
    """Guarda una factura emitida. `tipo_documento` y `condicion_iva` son nombres."""
    with Session() as session:
        tipo = (
            session.query(TiposDeDocumentos)
            .filter_by(nombre_de_tipo=tipo_documento)
            .one()
        )
        # La base ya existente guarda "Exento"; la interfaz histórica decía "Excento".
        indice = CONDICIONES_IVA.index(condicion_iva)
        condicion = session.query(CondicionFrenteIva).order_by("id").all()[indice]
        session.add(
            Facturas(
                id_cliente=id_cliente or None,
                tipo_de_documento_id=tipo.id,
                condicion_iva=condicion.id,
                productos=productos,
                valor_total=total,
                fecha=datetime.now(),
            )
        )
        session.commit()


def listar_facturas():
    """Devuelve todas las facturas, de la más reciente a la más antigua."""
    with Session() as session:
        return (
            session.query(Facturas)
            .options(
                joinedload(Facturas.tipo_de_documento),
                joinedload(Facturas.condicion_iva_rel),
            )
            .order_by(Facturas.fecha.desc(), Facturas.id.desc())
            .all()
        )
